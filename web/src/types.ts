export type Shot = {
  id: string;
  index: number;
  title: string;
  prompt: string;
  durationSeconds: number;
  uploads: { firstFrame?: string | null; lastFrame?: string | null };
  video?: { model: string; status: string; remoteJobId?: string | null; path?: string | null; errorMessage?: string | null } | null;
};

export type Project = {
  projectId: string;
  title: string;
  story: string;
  aspectRatio: "9:16" | "16:9";
  style: string;
  status: string;
  shots: Shot[];
  narration: { manuscript: string; audioPath?: string | null; status: string };
};

