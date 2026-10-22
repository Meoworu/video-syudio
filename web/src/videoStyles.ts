export const VIDEO_STYLE_PRESETS = [
  {
    value: "documentary",
    label: "纪录片风格",
    prompt: "Observational documentary style, natural available light, realistic colors and textures, candid unscripted feeling, restrained camera movement, authentic environmental details.",
  },
  {
    value: "cinematic_realism",
    label: "电影写实",
    prompt: "Cinematic live-action realism, natural textures, motivated lighting, subtle film grain, restrained color grading, deliberate camera movement.",
  },
  {
    value: "science_visualization",
    label: "科普可视化",
    prompt: "Clean scientific visualization, accurate scale and structure, clear cause-and-effect motion, macro and micro views, neutral lighting, uncluttered composition, no on-screen text.",
  },
  {
    value: "anime",
    label: "日系动画",
    prompt: "Japanese 2D animated film, expressive hand-drawn linework, painted backgrounds, controlled cel shading, fluid consistent motion, cinematic composition.",
  },
  {
    value: "3d_animation",
    label: "3D动画",
    prompt: "Stylized 3D animation, tactile materials, appealing simplified forms, soft global illumination, expressive motion, polished cinematic render.",
  },
  {
    value: "watercolor",
    label: "水彩绘本",
    prompt: "Watercolor storybook style, visible paper grain, translucent washes, soft edges, gentle colors, subtle hand-painted motion.",
  },
  {
    value: "paper_stop_motion",
    label: "纸艺定格",
    prompt: "Paper-craft stop-motion, layered cut paper, visible fibers and folded edges, handcrafted miniature sets, deliberate frame-by-frame motion.",
  },
  {
    value: "vintage_film",
    label: "复古胶片",
    prompt: "Vintage 35mm film look, organic grain, gentle halation, warm analog color response, soft contrast, natural camera movement.",
  },
] as const;

export type VideoStylePreset = (typeof VIDEO_STYLE_PRESETS)[number]["value"] | "custom";

export function getVideoStylePrompt(preset: VideoStylePreset) {
  return VIDEO_STYLE_PRESETS.find((item) => item.value === preset)?.prompt ?? "";
}

export function getVideoStyleLabel(prompt: string) {
  return VIDEO_STYLE_PRESETS.find((item) => item.prompt === prompt)?.label ?? prompt;
}
