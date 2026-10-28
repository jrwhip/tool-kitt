// @vitest-environment node
import { describe, expect, it } from 'vitest';
import {
  WINNING_LINES,
  applyMove,
  createGame,
  findWinningLine,
  readAuthoritativeState,
  type Board,
  type Cell,
  type GameState,
  type Mark,
  type MoveRejection,
  type WinningLine,
} from './game-rules';

const ALICE = 'alice';
const BOB = 'bob';
const PLAYERS = { X: ALICE, O: BOB } as const;

// Independently written ground truth for the eight lines (not read from the module).
const EXPECTED_LINES: readonly WinningLine[] = [
  [0, 1, 2],
  [3, 4, 5],
  [6, 7, 8],
  [0, 3, 6],
  [1, 4, 7],
  [2, 5, 8],
  [0, 4, 8],
  [2, 4, 6],
];

function newGame(): GameState {
  return createGame(PLAYERS);
}

/** Plays alternating cells starting with X (Alice); throws if any move is rejected. */
function play(cells: readonly number[]): GameState {
  let state = newGame();
  for (const cell of cells) {
    const turn = state.turn;
    if (turn === null) {
      throw new Error('game ended early in fixture');
    }
    const outcome = applyMove(state, { playerId: PLAYERS[turn], cell });
    if (!outcome.ok) {
      throw new Error(`fixture move ${cell} rejected: ${outcome.reason}`);
    }
    state = outcome.state;
  }
  return state;
}

function expectRejected(state: GameState, playerId: string, cell: number, reason: MoveRejection): void {
  const before = structuredClone(state);
  const outcome = applyMove(state, { playerId, cell });
  expect(outcome).toEqual({ ok: false, reason });
  expect(state).toEqual(before);
}

const DRAW_SEQUENCE = [0, 1, 2, 4, 3, 5, 7, 6, 8];
const WIN_ON_NINTH_SEQUENCE = [0, 1, 2, 5, 3, 6, 4, 7, 8];

describe('createGame', () => {
  it('starts with an empty board, X to move, and no result', () => {
    const state = newGame();
    expect(state.board).toEqual(Array<Cell>(9).fill(null));
    expect(state.turn).toBe('X');
    expect(state.participants).toEqual({ X: ALICE, O: BOB });
    expect(state.result).toBeNull();
  });

  it.each([
    ['empty X id', { X: '', O: BOB }],
    ['empty O id', { X: ALICE, O: '' }],
    ['identical ids', { X: ALICE, O: ALICE }],
  ])('rejects participants with %s', (_name, participants) => {
    expect(() => createGame(participants)).toThrow(RangeError);
  });
});

describe('WINNING_LINES', () => {
  it('lists exactly the 3 rows, 3 columns and 2 diagonals', () => {
    expect(WINNING_LINES).toHaveLength(8);
    expect(WINNING_LINES.map((l) => [...l].sort((a, b) => a - b))).toEqual(
      expect.arrayContaining(EXPECTED_LINES.map((l) => [...l])),
    );
  });
});

describe('applyMove turn and cell legality', () => {
  it('lets the player whose turn it is take an empty cell and passes the turn', () => {
    const state = newGame();
    const outcome = applyMove(state, { playerId: ALICE, cell: 4 });
    expect(outcome.ok).toBe(true);
    if (!outcome.ok) {
      return;
    }
    expect(outcome.state.board[4]).toBe('X');
    expect(outcome.state.board.filter((c) => c !== null)).toHaveLength(1);
    expect(outcome.state.turn).toBe('O');
    expect(outcome.state.result).toBeNull();
  });

  it('alternates back to X after O moves', () => {
    const state = play([4, 0]);
    expect(state.board[0]).toBe('O');
    expect(state.turn).toBe('X');
  });

  it('does not mutate the input state on an accepted move', () => {
    const state = newGame();
    const before = structuredClone(state);
    applyMove(state, { playerId: ALICE, cell: 0 });
    expect(state).toEqual(before);
  });

  it('rejects a participant moving out of turn and leaves the board unchanged', () => {
    expectRejected(newGame(), BOB, 0, 'not_your_turn');
  });

  it('rejects the previous mover moving twice in a row', () => {
    expectRejected(play([0]), ALICE, 1, 'not_your_turn');
  });

  it('rejects a move onto an occupied cell', () => {
    expectRejected(play([4]), BOB, 4, 'cell_occupied');
  });

  it('rejects the mover re-taking their own occupied cell', () => {
    expectRejected(play([4, 0]), ALICE, 0, 'cell_occupied');
  });

  it.each([-1, 9, 1.5, Number.NaN, Number.POSITIVE_INFINITY, 100])(
    'rejects out-of-grid or non-integer cell %s',
    (cell) => {
      expectRejected(newGame(), ALICE, cell, 'invalid_cell');
    },
  );

  it.each([0, 8])('accepts boundary cell %s', (cell) => {
    const outcome = applyMove(newGame(), { playerId: ALICE, cell });
    expect(outcome.ok).toBe(true);
  });

  it('reports wrong turn before an invalid cell', () => {
    expectRejected(newGame(), BOB, 99, 'not_your_turn');
  });
});

describe('applyMove non-participants', () => {
  const outsider = 'mallory';

  it('rejects an outsider on a fresh game', () => {
    expectRejected(newGame(), outsider, 0, 'not_a_participant');
  });

  it('rejects an outsider on an in-progress game', () => {
    expectRejected(play([0, 4]), outsider, 8, 'not_a_participant');
  });

  it('rejects an outsider on a finished game as a non-participant, not as finished', () => {
    expectRejected(play([0, 3, 1, 4, 2]), outsider, 8, 'not_a_participant');
  });

  it('rejects an outsider even when the move would be invalid', () => {
    expectRejected(newGame(), outsider, -1, 'not_a_participant');
  });

  it('treats participant ids as case-sensitive', () => {
    expectRejected(newGame(), 'Alice', 0, 'not_a_participant');
  });

  it('rejects an empty player id', () => {
    expectRejected(newGame(), '', 0, 'not_a_participant');
  });
});

describe('win detection', () => {
  function boardWithTwoOnLine(line: WinningLine, mark: Mark): Cell[] {
    const other: Mark = mark === 'X' ? 'O' : 'X';
    const board = Array<Cell>(9).fill(null);
    board[line[0]] = mark;
    board[line[1]] = mark;
    // Two opposing marks off the line; two cells can never form a line themselves.
    const off = [0, 1, 2, 3, 4, 5, 6, 7, 8].filter((i) => !line.includes(i));
    board[off[0]] = other;
    board[off[1]] = other;
    return board;
  }

  const cases = EXPECTED_LINES.flatMap((line) =>
    (['X', 'O'] as const).map((mark) => ({ line, mark, label: `${mark} on [${line.join(',')}]` })),
  );

  it.each(cases)('findWinningLine detects $label', ({ line, mark }) => {
    const board: Cell[] = Array<Cell>(9).fill(null);
    for (const i of line) {
      board[i] = mark;
    }
    expect(findWinningLine(board)).toEqual({ mark, line });
  });

  it.each(cases)('applyMove names winner and line for $label', ({ line, mark }) => {
    const state: GameState = {
      board: boardWithTwoOnLine(line, mark),
      turn: mark,
      participants: PLAYERS,
      result: null,
    };
    const outcome = applyMove(state, { playerId: PLAYERS[mark], cell: line[2] });
    expect(outcome.ok).toBe(true);
    if (!outcome.ok) {
      return;
    }
    expect(outcome.state.result).toEqual({
      outcome: 'win',
      winner: mark,
      winnerId: PLAYERS[mark],
      line,
    });
    expect(outcome.state.turn).toBeNull();
  });

  it('returns null for an empty board', () => {
    expect(findWinningLine(Array<Cell>(9).fill(null))).toBeNull();
  });

  it('returns null for two-in-a-row and for mixed lines', () => {
    const board: Board = ['X', 'X', 'O', null, 'O', null, null, 'X', 'X'];
    expect(findWinningLine(board)).toBeNull();
  });

  it('does not treat a line of empty cells as a win', () => {
    expect(findWinningLine(['X', null, null, 'O', null, null, null, null, null])).toBeNull();
  });

  it('finishes a real game with an X win on the top row', () => {
    const state = play([0, 3, 1, 4, 2]);
    expect(state.result).toEqual({ outcome: 'win', winner: 'X', winnerId: ALICE, line: [0, 1, 2] });
    expect(state.turn).toBeNull();
  });

  it('finishes a real game with an O win', () => {
    const state = play([0, 3, 1, 4, 8, 5]);
    expect(state.result).toEqual({ outcome: 'win', winner: 'O', winnerId: BOB, line: [3, 4, 5] });
    expect(state.turn).toBeNull();
  });
});

describe('draw detection', () => {
  it('declares a draw on a full board with no line', () => {
    const state = play(DRAW_SEQUENCE);
    expect(state.board.every((c) => c !== null)).toBe(true);
    expect(findWinningLine(state.board)).toBeNull();
    expect(state.result).toEqual({ outcome: 'draw' });
    expect(state.turn).toBeNull();
  });

  it('does not declare a draw while a cell is still empty', () => {
    const state = play(DRAW_SEQUENCE.slice(0, 8));
    expect(state.result).toBeNull();
    expect(state.turn).toBe('X');
  });

  it('scores a line completed on the ninth move as a win, not a draw', () => {
    const state = play(WIN_ON_NINTH_SEQUENCE);
    expect(state.board.every((c) => c !== null)).toBe(true);
    expect(state.result).toEqual({ outcome: 'win', winner: 'X', winnerId: ALICE, line: [0, 4, 8] });
    expect(state.turn).toBeNull();
  });
});

describe('finished games are immutable', () => {
  const finished: readonly (readonly [string, readonly number[]])[] = [
    ['won', [0, 3, 1, 4, 2]],
    ['drawn', DRAW_SEQUENCE],
  ];

  describe.each(finished)('after a %s game', (_label, moves) => {
    const emptyAfter = (state: GameState): number => state.board.findIndex((c) => c === null);

    it('rejects further moves from either participant and leaves the state unchanged', () => {
      const state = play(moves);
      const free = emptyAfter(state);
      const cell = free === -1 ? 0 : free;
      expectRejected(state, ALICE, cell, 'game_finished');
      expectRejected(state, BOB, cell, 'game_finished');
    });

    it('rejects a participant move onto an occupied cell as finished', () => {
      expectRejected(play(moves), ALICE, 0, 'game_finished');
    });

    it('rejects a finished-game move even with an invalid cell', () => {
      expectRejected(play(moves), BOB, 42, 'game_finished');
    });
  });

  it('rejects a move on a won game that still has empty cells', () => {
    const state = play([0, 3, 1, 4, 2]);
    expect(state.board.includes(null)).toBe(true);
    expectRejected(state, BOB, 8, 'game_finished');
  });

  it('rejects a move when turn is null even if result is missing', () => {
    const state: GameState = { ...newGame(), turn: null };
    expectRejected(state, ALICE, 0, 'game_finished');
  });
});

describe('readAuthoritativeState', () => {
  it('returns fields equal to the source state for a fresh game', () => {
    const state = newGame();
    expect(readAuthoritativeState(state)).toEqual(state);
  });

  it('reflects each accepted move', () => {
    let state = newGame();
    for (const cell of WIN_ON_NINTH_SEQUENCE) {
      const turn = state.turn as Mark;
      const outcome = applyMove(state, { playerId: PLAYERS[turn], cell });
      expect(outcome.ok).toBe(true);
      if (!outcome.ok) {
        return;
      }
      state = outcome.state;
      expect(readAuthoritativeState(state)).toEqual(state);
      expect(readAuthoritativeState(state).board[cell]).toBe(turn);
    }
  });

  it('is unchanged by a rejected move', () => {
    const state = play([0, 4]);
    const before = readAuthoritativeState(state);
    expect(applyMove(state, { playerId: 'mallory', cell: 8 }).ok).toBe(false);
    expect(applyMove(state, { playerId: ALICE, cell: 0 }).ok).toBe(false);
    expect(readAuthoritativeState(state)).toEqual(before);
  });

  it('exposes the win result with winner and line', () => {
    const read = readAuthoritativeState(play([0, 3, 1, 4, 2]));
    expect(read.result).toEqual({ outcome: 'win', winner: 'X', winnerId: ALICE, line: [0, 1, 2] });
    expect(read.turn).toBeNull();
  });

  it('exposes the draw result', () => {
    const read = readAuthoritativeState(play(DRAW_SEQUENCE));
    expect(read.result).toEqual({ outcome: 'draw' });
  });

  it('returns a deeply frozen copy', () => {
    const read = readAuthoritativeState(play([0, 3, 1, 4, 2]));
    expect(Object.isFrozen(read)).toBe(true);
    expect(Object.isFrozen(read.board)).toBe(true);
    expect(Object.isFrozen(read.participants)).toBe(true);
    expect(Object.isFrozen(read.result)).toBe(true);
    const result = read.result;
    expect(result !== null && result.outcome === 'win' && Object.isFrozen(result.line)).toBe(true);
  });

  it('freezes the draw result too', () => {
    expect(Object.isFrozen(readAuthoritativeState(play(DRAW_SEQUENCE)).result)).toBe(true);
  });

  it('throws when a caller writes to the returned copy, leaving the source intact', () => {
    const state = newGame();
    const before = structuredClone(state);
    const read = readAuthoritativeState(state);
    expect(() => {
      (read.board as Cell[])[0] = 'X';
    }).toThrow(TypeError);
    expect(() => {
      (read.participants as { X: string }).X = 'mallory';
    }).toThrow(TypeError);
    expect(state).toEqual(before);
  });

  it('is a copy: later mutation of the source board does not leak into the read', () => {
    const board: Cell[] = Array<Cell>(9).fill(null);
    const state: GameState = { board, turn: 'X', participants: PLAYERS, result: null };
    const read = readAuthoritativeState(state);
    board[0] = 'O';
    expect(read.board[0]).toBeNull();
  });
});
