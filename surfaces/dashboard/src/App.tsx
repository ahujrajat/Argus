import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "./components/Layout";
import { FindingsPage } from "./pages/findings/FindingsPage";
import { RunsPage } from "./pages/runs/RunsPage";
import { CostPage } from "./pages/cost/CostPage";
import { PipelinePage } from "./pages/pipeline/PipelinePage";
import { FixReviewPage } from "./pages/fixes/FixReviewPage";

const qc = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/findings" replace />} />
            <Route path="/findings" element={<FindingsPage />} />
            <Route path="/runs" element={<RunsPage />} />
            <Route path="/cost" element={<CostPage />} />
            <Route path="/pipeline" element={<PipelinePage />} />
            <Route path="/fixes" element={<FixReviewPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
