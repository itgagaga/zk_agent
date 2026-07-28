/** 课表课程配色（参考 Timetable / shadcn Class Timetable 的色块区分思路） */
export const COURSE_PALETTE = [
  { bg: '#fff0e8', border: '#CF4500', text: '#9A3A0A' },
  { bg: '#eef3fc', border: '#3860BE', text: '#2a4a8f' },
  { bg: '#edf7f1', border: '#2D6A4F', text: '#1b4332' },
  { bg: '#f5eef8', border: '#6B4C9A', text: '#4a3470' },
  { bg: '#fceef3', border: '#C9184A', text: '#8b1234' },
  { bg: '#fef6e8', border: '#B7791F', text: '#7a5015' },
  { bg: '#e8f6f8', border: '#2C7A7B', text: '#1d5354' },
  { bg: '#f0f0f5', border: '#4A5568', text: '#2d3748' },
]

export function getCourseStyle(colorIndex = 0) {
  const c = COURSE_PALETTE[colorIndex % COURSE_PALETTE.length]
  return {
    '--course-bg': c.bg,
    '--course-border': c.border,
    '--course-text': c.text,
  }
}

export function getColorIndex(name, legendMap = {}) {
  if (legendMap[name] !== undefined) return legendMap[name]
  let h = 0
  for (let i = 0; i < (name || '').length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0
  return h % COURSE_PALETTE.length
}
