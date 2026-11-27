// 여러 화면에서 같이 쓰는 작은 도우미들

const EMOJI = { 화재: "🔥", 지진: "🌏", 엘리베이터: "🛗", 홍수: "🌊" };
export const categoryEmoji = (category) => EMOJI[category] ?? "🚨";

// 위험도 비율에 따라 색 단계
export function riskLevel(risk, maxRisk) {
  const ratio = maxRisk ? risk / maxRisk : 0;
  if (ratio >= 2 / 3) return "high";
  if (ratio >= 1 / 3) return "mid";
  return "low";
}
