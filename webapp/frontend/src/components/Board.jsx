import { Chessboard } from 'react-chessboard'

export default function Board({ fen, arrows = [], boardWidth = 520 }) {
  return (
    <Chessboard
      position={fen || 'start'}
      customArrows={arrows}
      arePiecesDraggable={false}
      boardWidth={boardWidth}
      customBoardStyle={{
        borderRadius: '4px',
        boxShadow: '0 4px 24px rgba(0,0,0,0.6)',
      }}
      customDarkSquareStyle={{ backgroundColor: '#769656' }}
      customLightSquareStyle={{ backgroundColor: '#eeeed2' }}
    />
  )
}
