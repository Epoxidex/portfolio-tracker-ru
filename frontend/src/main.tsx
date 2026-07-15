import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

function MigrationPlaceholder() {
  return null;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MigrationPlaceholder />
  </StrictMode>,
);
