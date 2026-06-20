# DOCUMENT 4: FRONTEND ARCHITECTURE

This document details the frontend architecture for the GitHub Repository Intelligence Platform, built using Next.js 16 (App Router), TypeScript, Tailwind CSS, shadcn/ui, Zustand, and TanStack Query.

---

## 4.1 Route Map

### 1. Landing Page
*   **ROUTE**: `/`
*   **COMPONENT**: `LandingPage`
*   **PURPOSE**: Marketing interface showcasing platform features, high-level process flow, and the "Sign in with GitHub" authentication portal.
*   **AUTH**: public
*   **QUERIES**: None.
*   **MUTATIONS**: None.

### 2. Dashboard Page
*   **ROUTE**: `/dashboard`
*   **COMPONENT**: `DashboardPage`
*   **PURPOSE**: Displays a list of the user's analyzed repositories, their indexing state, and shortcuts to view results or start a new analysis.
*   **AUTH**: required
*   **QUERIES**: `GET /api/v1/repositories` (list user repos)
*   **MUTATIONS**: `DELETE /api/v1/repositories/{id}` (remove repository entry)

### 3. Submit Repository Page
*   **ROUTE**: `/repositories/new`
*   **COMPONENT**: `NewRepositoryPage`
*   **PURPOSE**: Forms interface allowing the user to submit a public GitHub repository link for analysis.
*   **AUTH**: required
*   **QUERIES**: None.
*   **MUTATIONS**: `POST /api/v1/repositories` (register repository URL)

### 4. Repository Analysis Status Page
*   **ROUTE**: `/repositories/[id]`
*   **COMPONENT**: `RepositoryStatusPage`
*   **PURPOSE**: Real-time progress tracker monitoring the active LangGraph execution steps via WebSockets.
*   **AUTH**: required
*   **QUERIES**: 
    *   `GET /api/v1/repositories/{id}` (get repository profile)
    *   `GET /api/v1/repositories/{id}/analysis/{job_id}` (get active job metadata)
*   **MUTATIONS**: `POST /api/v1/repositories/{id}/analyze` (trigger a new run)

### 5. Repository Review Page (HiTL Portal)
*   **ROUTE**: `/repositories/[id]/review`
*   **COMPONENT**: `RepositoryReviewPage`
*   **PURPOSE**: Interactive, checklist-driven layout where users inspect, modify, and confirm AI-extracted code facts.
*   **AUTH**: required
*   **QUERIES**:
    *   `GET /api/v1/reviews/pending` (find target active review id)
    *   `GET /api/v1/reviews/{review_id}` (retrieve facts checklist)
*   **MUTATIONS**:
    *   `PATCH /api/v1/reviews/{review_id}/facts` (submit approved/edited/rejected facts payload)
    *   `POST /api/v1/reviews/{review_id}/reject` (reject entire run)

### 6. Outputs Portal Page
*   **ROUTE**: `/repositories/[id]/outputs`
*   **COMPONENT**: `OutputsPage`
*   **PURPOSE**: Multi-tab interface displaying generated technical copy: Resume Bullets, LinkedIn Project Summary, README.md, and Portfolio Page.
*   **AUTH**: required
*   **QUERIES**:
    *   `GET /api/v1/repositories/{id}/outputs` (list outputs)
    *   `GET /api/v1/outputs/{output_id}` (fetch active output content)
*   **MUTATIONS**:
    *   `POST /api/v1/outputs/{output_id}/regenerate` (trigger version bump run)
    *   `GET /api/v1/outputs/{output_id}/download` (retrieve S3 presigned URL)

### 7. Settings Page
*   **ROUTE**: `/settings`
*   **COMPONENT**: `SettingsPage`
*   **PURPOSE**: Details user profile settings, account linkages, API usage limits, and daily token metrics.
*   **AUTH**: required
*   **QUERIES**: 
    *   `GET /api/v1/auth/me` (retrieve user profile details)
    *   `GET /api/v1/usage_metrics` (fetch API token spending records)
*   **MUTATIONS**: None.

---

## 4.2 Component Trees

### 1. RepositoryReviewPage (Interactive Checklist Portal)
```
RepositoryReviewPage
  ├── StickyReviewHeader
  │     ├── RepositoryTitle (owner / name)
  │     └── ReviewSummary (visual count of approved, edited, rejected, and pending facts)
  ├── FactReviewLayout (Split view or single column layout)
  │     ├── FactReviewPanel
  │     │     └── FactList
  │     │           └── FactCard (Repeated container representing a single claim)
  │     │                 ├── FactTypeBadge (e.g. Technology Used vs Pattern)
  │     │                 ├── FactTextContainer (In-line editable input if 'Edit' is active)
  │     │                 ├── FactEvidenceDrawerTrigger (Toggles detail code tray)
  │     │                 └── FactActions (Button toggles: Approve [Green] | Reject [Red] | Edit [Blue])
  │     └── EvidenceViewerPanel (Visual code editor pane showing line-number highlight)
  │           ├── FilePathBreadcrumb
  │           └── CodeSnippetViewer (Syntax highlighted code block displaying cited lines)
  └── FloatingActionBar
        ├── RejectionCancelDialog (Toggles full pipeline cancel run)
        └── SubmitReviewButton (Submits state delta payload. Disabled until 100% of facts are reviewed)
```

### 2. RepositoryStatusPage (Progress & Real-Time Tracking)
```
RepositoryStatusPage
  ├── StatusHeader
  │     ├── RepositoryHeaderSummary
  │     └── JobStatusBadge (queued, running, interrupted, complete, failed)
  ├── LiveProgressTimeline
  │     └── TimelineStep (List of LangGraph execution nodes with state: complete, active, pending, error)
  │           ├── StepIndicatorIcon (Checkmark, spinner, warning sign, or empty circle)
  │           ├── StepTitle (e.g. fetch_repository_metadata)
  │           └── StepDurationTicker (Live stopwatch running during active step)
  ├── ConsoleLogViewer (Scrollable viewport printing stdout-style logs of the run)
  └── StatusActionGate
        └── AwaitingReviewBanner (CTA overlay directing user to /review when status is 'interrupted')
```

### 3. OutputsPage (Finalized Copies & Export Options)
```
OutputsPage
  ├── OutputHeader
  │     ├── PageTitle
  │     └── GlobalExportDropdown (Download MD/PDF/JSON bundle)
  └── TabbedContainer (shadcn/ui tabs layout)
        ├── TabTriggerList
        │     ├── ResumeBulletsTabTrigger
        │     ├── LinkedInSummaryTabTrigger
        │     ├── ReadmeTabTrigger
        │     └── PortfolioDocTabTrigger
        └── TabContentWrapper (Displays active tab component)
              ├── OutputViewer
              │     ├── VersionSelector (Select between version v1, v2, etc.)
              │     ├── LLMModelBadge (Details model used + token weight)
              │     ├── OutputContentMarkdown (Rendered markdown content block)
              │     └── OutputActions
              │           ├── ClipboardCopyButton (Copies text directly to system clipboard)
              │           ├── SingleFileDownloadButton (Triggers API presigned URL fetch)
              │           └── RegenerateOutputButton (Opens customization options and triggers rerun)
              └── CustomizationSidebar (Inputs to customize output e.g. target job description)
```

---

## 4.3 Client & Server State Design

### Client State: Zustand Stores

#### 1. `useAnalysisStore`
This store tracks active job executions, manages real-time WebSocket connection states, and logs pipeline events.

```typescript
interface AnalysisJob {
  id: string;
  repository_id: string;
  status: 'queued' | 'running' | 'interrupted' | 'complete' | 'failed' | 'timed_out';
  current_node: string | null;
  error_message: string | null;
}

interface WSEvent {
  event: 'job_queued' | 'job_started' | 'node_changed' | 'review_required' | 'generation_started' | 'job_complete' | 'job_failed';
  job_id: string;
  data: Record<string, any>;
}

interface AnalysisState {
  currentJob: AnalysisJob | null;
  wsStatus: 'connecting' | 'connected' | 'disconnected';
  latestEvent: WSEvent | null;
  connectWS: (userId: string, token: string) => void;
  disconnectWS: () => void;
  setCurrentJob: (job: AnalysisJob | null) => void;
  handleWSEvent: (event: WSEvent) => void;
  reset: () => void;
}
```

#### 2. `useReviewStore`
This store manages local interactive states during the fact-review workflow, tracking user selection changes before API dispatch.

```typescript
interface FactDecision {
  id: string;
  decision: 'approve' | 'reject' | 'edit';
  editedText?: string;
}

interface ReviewState {
  reviewId: string | null;
  facts: Record<string, FactDecision>; // Map of code_fact_id to user decision state
  activeFactId: string | null;         // Selected fact currently shown in the Code Evidence panel
  initializeReview: (reviewId: string, factIds: string[]) => void;
  setFactDecision: (factId: string, decision: 'approve' | 'reject' | 'edit', text?: string) => void;
  setActiveFact: (factId: string) => void;
  getSummary: () => { approvedCount: number; rejectedCount: number; editedCount: number; pendingCount: number };
  reset: () => void;
}
```

---

### Server State: TanStack Query (React Query)

#### Query Keys Factory
```typescript
export const queryKeys = {
  repositories: {
    all: ['repositories'] as const,
    list: (page: number, size: number) => [...queryKeys.repositories.all, 'list', { page, size }] as const,
    detail: (id: string) => [...queryKeys.repositories.all, 'detail', id] as const,
  },
  jobs: {
    all: ['jobs'] as const,
    status: (jobId: string) => [...queryKeys.jobs.all, 'status', jobId] as const,
    facts: (jobId: string) => [...queryKeys.jobs.all, 'facts', jobId] as const,
  },
  reviews: {
    all: ['reviews'] as const,
    detail: (reviewId: string) => [...queryKeys.reviews.all, 'detail', reviewId] as const,
    pending: () => [...queryKeys.reviews.all, 'pending'] as const,
  },
  outputs: {
    all: ['outputs'] as const,
    list: (repoId: string) => [...queryKeys.outputs.all, 'list', repoId] as const,
    detail: (outputId: string) => [...queryKeys.outputs.all, 'detail', outputId] as const,
  }
};
```

#### Mutation Patterns

1.  **Submit Facts Review (`PATCH /reviews/{id}/facts`)**:
    ```typescript
    const useSubmitReviewMutation = (reviewId: string) => {
      const queryClient = useQueryClient();
      const router = useRouter();
      
      return useMutation({
        mutationFn: (payload: ReviewSubmissionPayload) => 
          api.patch(`/reviews/${reviewId}/facts`, payload),
        onMutate: async (newReview) => {
          // Cancel outgoing queries to prevent overwrites
          await queryClient.cancelQueries({ queryKey: queryKeys.reviews.detail(reviewId) });
          // Snapshot previous review state for rollback
          const previousReview = queryClient.getQueryData(queryKeys.reviews.detail(reviewId));
          // Optimistically update review status locally to simulate immediate response
          queryClient.setQueryData(queryKeys.reviews.detail(reviewId), (old: any) => ({
            ...old,
            status: 'approved'
          }));
          return { previousReview };
        },
        onError: (err, newReview, context) => {
          // Rollback cache to snapshot state on server failure
          queryClient.setQueryData(queryKeys.reviews.detail(reviewId), context?.previousReview);
          toast.error("Failed to submit review. Try again.");
        },
        onSuccess: (data) => {
          toast.success("Facts approved! Resuming pipeline...");
          router.push(`/repositories/${data.repository_id}/status`);
        },
        onSettled: () => {
          queryClient.invalidateQueries({ queryKey: queryKeys.reviews.all });
        }
      });
    };
    ```

2.  **Output Re-generation (`POST /outputs/{id}/regenerate`)**:
    *   Triggers job spin-up. Invalidates `queryKeys.outputs.list` and navigates to the Status page to display the compilation progress.

3.  **Get Presigned Download Link (`GET /outputs/{id}/download`)**:
    *   Initiated on user click. Does not modify cache states. Safely opens the fetched presigned URL in a secure, target-blank browser tab for download routing.

---

## 4.4 The Review Page — Detailed UX Flow

1.  **Landing**:
    *   The user is on the platform and receives a `review_required` WebSocket event notification, or they land directly on `/repositories/[id]/review` via the status page link.
2.  **Loading Data**:
    *   The page mounts and displays a skeleton loading layout. It queries `GET /api/v1/reviews/{review_id}` to fetch the list of facts.
3.  **Initializing State**:
    *   The retrieved facts are loaded into the local Zustand `useReviewStore`. The page displays the layout: 
        *   **Left Column**: A vertical list of facts (FactList).
        *   **Right Column**: An interactive editor window displaying the highlighted code snippet (EvidenceViewerPanel).
        *   **Footer**: A progress tracker summary bar.
4.  **Selecting Fact Detail**:
    *   The first fact is highlighted by default. The `activeFactId` is set in the store. The `EvidenceViewerPanel` reads the active fact's `evidence_file_path`, syntax-highlights the `evidence_snippet`, and displays a file outline with matching line numbers (e.g. lines 45-62).
5.  **Review Decision Input**:
    *   The user reviews the statement. They have three direct actions:
        *   **Approve**: Marks the fact as verified (turns card background to green).
        *   **Reject**: Excludes the fact from document compiler input contexts (turns card background to muted red).
        *   **Edit**: Toggles the card text block into a text input, permitting inline textual corrections. Once corrected and saved, the card updates to an 'edited' state (turns background to blue).
6.  **Summary Calculation**:
    *   As the user proceeds, the `ReviewSummary` bar dynamically updates: `12 / 15 Facts Reviewed (10 Approved, 1 Edited, 1 Rejected, 3 Pending)`. The main **Confirm Facts and Generate Resume** CTA button remains disabled.
7.  **Submission Preparation**:
    *   Once the 15th fact receives a decision, the submit button is enabled.
8.  **Optimistic Dispatch**:
    *   When the user clicks the submit button:
        1.  The UI shows a loading spinner on the button.
        2.  The mutation is dispatched to `PATCH /api/v1/reviews/{review_id}/facts`.
        3.  The client optimistically updates the cache and immediately routes the user back to the Status page `/repositories/[id]`.
9.  **Error Recovery**:
    *   If the backend throws a database transaction timeout or a validation failure (e.g. 500/400 error):
        1.  The router halts the redirection.
        2.  The TanStack Query mutation catches the error and rollbacks the state cache to the pre-submission snapshot.
        3.  A red toast alert is displayed: `System Error: Unable to verify facts. Please try submitting again.`
        4.  The user remains on the review page with their edits intact.
