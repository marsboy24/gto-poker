"""
GTO Poker Backend — FastAPI Application
Endpoints for pre-flop ranges and post-flop MCCFR solving.
"""

import json
import os
import asyncio
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from preflop.generator import generate_ranges, POSITIONS
from solver.cfr import CFRSolver
from solver.game_state import GameState

app = FastAPI(title="GTO Poker API", version="1.0.0")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Pre-flop ranges (loaded once at startup)
# ---------------------------------------------------------------------------

RANGES_PATH = os.path.join(os.path.dirname(__file__), "preflop", "ranges.json")
_preflop_ranges: Dict[str, Any] = {}


def _load_or_generate_ranges() -> Dict[str, Any]:
    """Load ranges from JSON if it exists, otherwise generate and cache."""
    if os.path.exists(RANGES_PATH):
        with open(RANGES_PATH, "r") as f:
            return json.load(f)
    else:
        print("ranges.json not found — generating on-the-fly...")
        ranges = generate_ranges()
        os.makedirs(os.path.dirname(RANGES_PATH), exist_ok=True)
        with open(RANGES_PATH, "w") as f:
            json.dump(ranges, f, indent=2)
        return ranges


@app.on_event("startup")
async def startup_event() -> None:
    global _preflop_ranges
    _preflop_ranges = _load_or_generate_ranges()
    print(f"Loaded pre-flop ranges for player counts: {list(_preflop_ranges.keys())}")


# ---------------------------------------------------------------------------
# Pre-flop endpoints
# ---------------------------------------------------------------------------

@app.get("/api/preflop/positions")
async def get_positions(players: int = Query(..., ge=2, le=9)) -> List[str]:
    """Return the list of position names for a given player count."""
    if players not in POSITIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported player count: {players}")
    return POSITIONS[players]


@app.get("/api/preflop/range")
async def get_range(
    players: int = Query(..., ge=2, le=9),
    position: str = Query(...),
    action: Optional[str] = Query(None),
) -> Dict[str, float]:
    """
    Return the pre-flop range for a given position and player count.

    If action is provided, returns frequencies for that action only.
    Otherwise returns open_raise frequencies (most common use case).
    """
    key = str(players)
    if key not in _preflop_ranges:
        raise HTTPException(status_code=404, detail=f"No ranges for {players} players")

    pos_data = _preflop_ranges[key].get(position)
    if pos_data is None:
        available = list(_preflop_ranges[key].keys())
        raise HTTPException(
            status_code=404,
            detail=f"Position '{position}' not found for {players} players. Available: {available}",
        )

    if action is not None:
        action_data = pos_data.get(action)
        if action_data is None:
            available_actions = list(pos_data.keys())
            raise HTTPException(
                status_code=404,
                detail=f"Action '{action}' not found. Available: {available_actions}",
            )
        return action_data

    # Default: return open_raise frequencies
    return pos_data.get("open_raise", {})


# ---------------------------------------------------------------------------
# Post-flop solve — REST endpoint
# ---------------------------------------------------------------------------

class PostFlopRequest(BaseModel):
    board: List[str]
    hero_hand: List[str]
    players: int
    pot: float
    stacks: List[float]
    hero_position: int
    betting_history: List[Dict[str, Any]] = []


def _build_default_opponent_range(hero_hand: List[str], board: List[str]) -> List[List[str]]:
    """Build a simple default opponent range (top ~30% of hands, minus blockers)."""
    all_ranks = 'AKQJT98765432'
    all_suits = 'shdc'
    blocked = set(hero_hand + board)

    all_cards = [r + s for r in all_ranks for s in all_suits if (r + s) not in blocked]

    # Generate random pairs as opponent combos (simplified)
    import random
    combos = []
    for _ in range(50):
        if len(all_cards) >= 2:
            sample = random.sample(all_cards, 2)
            combos.append(sample)
    return combos


@app.post("/api/postflop/solve")
async def solve_postflop(req: PostFlopRequest) -> Dict[str, Any]:
    """
    Run MCCFR solver for post-flop situation.
    Returns strategy, equity, and iteration count.
    """
    if req.players < 2 or req.players > 9:
        raise HTTPException(status_code=400, detail="players must be between 2 and 9")
    if len(req.stacks) < req.players:
        raise HTTPException(status_code=400, detail="stacks length must match players count")
    if req.hero_position >= req.players:
        raise HTTPException(status_code=400, detail="hero_position out of range")

    board_len = len(req.board)
    if board_len == 3:
        street = "flop"
    elif board_len == 4:
        street = "turn"
    elif board_len == 5:
        street = "river"
    else:
        raise HTTPException(status_code=400, detail="board must have 3, 4, or 5 cards")

    state = GameState(
        players=req.players,
        stacks=list(req.stacks),
        pot=req.pot,
        board=req.board,
        street=street,
        hero_position=req.hero_position,
        betting_history=list(req.betting_history),
        active_players=list(range(req.players)),
    )

    opp_range = _build_default_opponent_range(req.hero_hand, req.board)

    solver = CFRSolver()

    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: solver.solve(state, iterations=1000, hero_hand=req.hero_hand, opponent_range=opp_range),
    )

    return result


# ---------------------------------------------------------------------------
# Post-flop solve — WebSocket streaming endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/postflop/solve")
async def ws_solve_postflop(websocket: WebSocket) -> None:
    """
    WebSocket endpoint that streams MCCFR iterations.
    Client sends JSON matching PostFlopRequest.
    Server streams: {iteration, strategy, equity} every 100 iterations.
    """
    await websocket.accept()

    try:
        data = await websocket.receive_json()

        board_len = len(data.get("board", []))
        if board_len == 3:
            street = "flop"
        elif board_len == 4:
            street = "turn"
        elif board_len == 5:
            street = "river"
        else:
            await websocket.send_json({"error": "board must have 3, 4, or 5 cards"})
            await websocket.close()
            return

        players = int(data.get("players", 2))
        stacks = data.get("stacks", [100.0] * players)
        hero_position = int(data.get("hero_position", 0))
        hero_hand = data.get("hero_hand", [])
        board = data.get("board", [])
        pot = float(data.get("pot", 10.0))
        betting_history = data.get("betting_history", [])

        state = GameState(
            players=players,
            stacks=list(stacks),
            pot=pot,
            board=board,
            street=street,
            hero_position=hero_position,
            betting_history=list(betting_history),
            active_players=list(range(players)),
        )

        opp_range = _build_default_opponent_range(hero_hand, board)
        solver = CFRSolver()

        # Run solver in executor and stream results
        loop = asyncio.get_event_loop()

        def run_streaming():
            results = []
            for chunk in solver.solve_streaming(
                state,
                total_iterations=1000,
                report_every=100,
                hero_hand=hero_hand,
                opponent_range=opp_range,
            ):
                results.append(chunk)
            return results

        results = await loop.run_in_executor(None, run_streaming)

        for chunk in results:
            try:
                await websocket.send_json(chunk)
                await asyncio.sleep(0)  # yield control
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "ranges_loaded": str(len(_preflop_ranges) > 0)}
