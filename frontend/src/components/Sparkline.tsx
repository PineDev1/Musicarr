type Series = { label: string; color: string; values: number[] }

export function Sparkline({
  series,
  height = 60,
  width = 320,
}: {
  series: Series[]
  height?: number
  width?: number
}) {
  const allValues = series.flatMap((s) => s.values)
  const max = Math.max(1, ...allValues)
  const pointCount = Math.max(1, ...series.map((s) => s.values.length))
  const stepX = pointCount > 1 ? width / (pointCount - 1) : width

  const toPoints = (values: number[]) =>
    values
      .map((v, i) => `${(i * stepX).toFixed(1)},${(height - (v / max) * height).toFixed(1)}`)
      .join(' ')

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      preserveAspectRatio="none"
      role="img"
      aria-label={series.map((s) => s.label).join(', ')}
    >
      {series.map((s) => (
        <polyline
          key={s.label}
          points={toPoints(s.values)}
          fill="none"
          stroke={s.color}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}
    </svg>
  )
}
