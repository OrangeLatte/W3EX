"use client";

/** 市场体制仪表盘：半圆弧三段色带 + 指针 + 分值（-100 ~ +100） */
export function RegimeGauge({ score }: { score: number }) {
  const clamped = Math.max(-100, Math.min(100, score));
  // 半圆从左(-100)到右(+100)，角度 180°→0°
  const angle = 180 - ((clamped + 100) / 200) * 180;
  const rad = (deg: number) => (deg * Math.PI) / 180;
  const cx = 110;
  const cy = 100;
  const R = 82;
  const arc = (from: number, to: number, color: string, width: number) => {
    const a1 = rad(from);
    const a2 = rad(to);
    const x1 = cx + R * Math.cos(a1);
    const y1 = cy - R * Math.sin(a1);
    const x2 = cx + R * Math.cos(a2);
    const y2 = cy - R * Math.sin(a2);
    return (
      <path
        key={`${from}-${to}`}
        d={`M ${x1} ${y1} A ${R} ${R} 0 0 1 ${x2} ${y2}`}
        stroke={color}
        strokeWidth={width}
        fill="none"
        strokeLinecap="butt"
      />
    );
  };
  const needleRad = rad(angle);
  const nx = cx + (R - 14) * Math.cos(needleRad);
  const ny = cy - (R - 14) * Math.sin(needleRad);
  const tone = clamped >= 20 ? "#22e5a1" : clamped <= -20 ? "#ff4d67" : "#ffb020";
  return (
    <svg width="100%" height={118} viewBox="0 0 220 118" className="max-w-[240px]">
      {arc(180, 138, "#ff4d67", 10)}
      {arc(138, 108, "#8a3a4a", 10)}
      {arc(108, 72, "#3a4a8a", 10)}
      {arc(72, 42, "#2a7a5a", 10)}
      {arc(42, 0, "#22e5a1", 10)}
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={tone} strokeWidth="2.5" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="5" fill={tone} />
      <text x={cx} y={cy + 16} textAnchor="middle" fill={tone} className="num" fontSize="15" fontWeight="600">
        {clamped > 0 ? `+${clamped.toFixed(0)}` : clamped.toFixed(0)}
      </text>
    </svg>
  );
}
