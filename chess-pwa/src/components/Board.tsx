import { Chessboard } from 'react-chessboard'

export interface Arrow { startSquare: string; endSquare: string; color: string }

interface Props {
  fen: string
  arrows?: Arrow[]
  boardWidth?: number
}

export default function Board({ fen, arrows = [], boardWidth = 520 }: Props) {
  return (
    <Chessboard
      options={{
        position: fen,
        boardStyle: { width: boardWidth, height: boardWidth },
        allowDragging: false,
        arrows,
        animationDurationInMs: 150,
      }}
    />
  )
}
