import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

function App() {
  return <main style={{ padding: 32, fontFamily: "system-ui" }}>video-studio</main>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

