export type PlayerId = string;
export type Mark = 'X' | 'O';
export type Cell = Mark | null;
/** Row-major, indices 0..8 (index = row * 3 + col). */
export type Board = readonly Cell[];
export type WinningLine = readonly [number, number, number];

export type GameResult =
  | {
      readonly outcome: 'win';
      readonly winner: Mark;
      readonly winnerId: PlayerId;
      readonly line: WinningLine;
    }
  | { readonly outcome: 'draw' };

export interface GameState {
  readonly board: Board;
  /** Null once the game has a result. */
  readonly turn: Mark | null;
  readonly participants: { readonly X: PlayerId; readonly O: PlayerId };
  readonly result: GameResult | null;
}

export interface Move {
  readonly playerId: PlayerId;
  readonly cell: number;
}

export type MoveRejection =
  | 'not_a_participant'
  | 'game_finished'
  | 'not_your_turn'
  | 'invalid_cell'
  | 'cell_occupied';

export type MoveOutcome =
  | { readonly ok: true; readonly state: GameState }
  | { readonly ok: false; readonly reason: MoveRejection };

export const WINNING_LINES: readonly WinningLine[] = [
  [0, 1, 2],
  [3, 4, 5],
  [6, 7, 8],
  [0, 3, 6],
  [1, 4, 7],
  [2, 5, 8],
  [0, 4, 8],
  [2, 4, 6],
];

const BOARD_SIZE = 9;

/**
 * The module trusts the player ids it receives; callers must derive them from
 * a verified identity, never from client-supplied request fields.
 */
export function createGame(participants: {
  readonly X: PlayerId;
  readonly O: PlayerId;
}): GameState {
  if (participants.X === '' || participants.O === '' || participants.X === participants.O) {
    throw new RangeError('participants must be two distinct non-empty player ids');
  }
  return {
    board: Array<Cell>(BOARD_SIZE).fill(null),
    turn: 'X',
    participants: { X: participants.X, O: participants.O },
    result: null,
  };
}

export function findWinningLine(
  board: Board,
): { readonly mark: Mark; readonly line: WinningLine } | null {
  for (const line of WINNING_LINES) {
    const mark = board[line[0]];
    if (mark !== null && mark !== undefined && board[line[1]] === mark && board[line[2]] === mark) {
      return { mark, line };
    }
  }
  return null;
}

export function applyMove(state: GameState, move: Move): MoveOutcome {
  const { participants } = state;
  if (move.playerId !== participants.X && move.playerId !== participants.O) {
    return { ok: false, reason: 'not_a_participant' };
  }
  if (state.result !== null || state.turn === null) {
    return { ok: false, reason: 'game_finished' };
  }
  if (participants[state.turn] !== move.playerId) {
    return { ok: false, reason: 'not_your_turn' };
  }
  const { cell } = move;
  if (!Number.isInteger(cell) || cell < 0 || cell >= BOARD_SIZE) {
    return { ok: false, reason: 'invalid_cell' };
  }
  if (state.board[cell] !== null) {
    return { ok: false, reason: 'cell_occupied' };
  }

  const mark = state.turn;
  const board = state.board.map((c, i): Cell => (i === cell ? mark : c));
  const win = findWinningLine(board);

  if (win !== null) {
    return {
      ok: true,
      state: {
        board,
        turn: null,
        participants,
        result: {
          outcome: 'win',
          winner: win.mark,
          winnerId: participants[win.mark],
          line: win.line,
        },
      },
    };
  }
  if (!board.includes(null)) {
    return { ok: true, state: { board, turn: null, participants, result: { outcome: 'draw' } } };
  }
  return {
    ok: true,
    state: { board, turn: mark === 'X' ? 'O' : 'X', participants, result: null },
  };
}

export function readAuthoritativeState(state: GameState): GameState {
  const result: GameResult | null =
    state.result === null
      ? null
      : state.result.outcome === 'win'
        ? Object.freeze({
            outcome: 'win',
            winner: state.result.winner,
            winnerId: state.result.winnerId,
            line: Object.freeze([...state.result.line]) as unknown as WinningLine,
          })
        : Object.freeze({ outcome: 'draw' });
  return Object.freeze({
    board: Object.freeze([...state.board]),
    turn: state.turn,
    participants: Object.freeze({ X: state.participants.X, O: state.participants.O }),
    result,
  });
}
