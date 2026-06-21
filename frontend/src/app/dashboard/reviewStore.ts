import { create } from "zustand";

export interface Fact {
  category: string;
  claim: string;
  source_file: string;
  snippet: string;
  ats_impact: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface ReviewState {
  facts: Fact[];
  suggestedQuestions: string[];
  chatHistory: ChatMessage[];
  isLoadingFacts: boolean;
  isSendingMessage: boolean;
  isResuming: boolean;
  error: string | null;
  
  // Actions
  fetchFacts: (repositoryId: string) => Promise<void>;
  setFacts: (facts: Fact[]) => void;
  updateFact: (index: number, updatedFact: Partial<Fact>) => void;
  deleteFact: (index: number) => void;
  addFact: (fact: Fact) => void;
  
  sendChatMessage: (jobId: string, message: string) => Promise<void>;
  submitReview: (jobId: string, routerPush: () => void) => Promise<void>;
  clearStore: () => void;
}

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export const useReviewStore = create<ReviewState>((set, get) => ({
  facts: [],
  suggestedQuestions: [],
  chatHistory: [
    {
      role: "assistant",
      content: "Hello! I am your AI RepoProof pairing partner. Feel free to ask me questions about the code, request changes to any claim, or ask me to draft new resume points based on your codebase!"
    }
  ],
  isLoadingFacts: false,
  isSendingMessage: false,
  isResuming: false,
  error: null,

  fetchFacts: async (repositoryId: string) => {
    set({ isLoadingFacts: true, error: null });
    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/repositories/${repositoryId}/analysis-result`);
      if (!response.ok) {
        throw new Error("Failed to fetch intermediate analysis results.");
      }
      const data = await response.json();
      set({
        facts: data.facts || [],
        suggestedQuestions: data.suggested_questions || [],
        isLoadingFacts: false
      });
    } catch (err: any) {
      set({ error: err.message || "Failed to load facts", isLoadingFacts: false });
    }
  },

  setFacts: (facts) => set({ facts }),

  updateFact: (index, updatedFact) => {
    const currentFacts = [...get().facts];
    if (currentFacts[index]) {
      currentFacts[index] = { ...currentFacts[index], ...updatedFact };
      set({ facts: currentFacts });
    }
  },

  deleteFact: (index) => {
    const currentFacts = get().facts.filter((_, i) => i !== index);
    set({ facts: currentFacts });
  },

  addFact: (fact) => {
    set({ facts: [...get().facts, fact] });
  },

  sendChatMessage: async (jobId, message) => {
    if (!message.trim()) return;
    
    const userMsg: ChatMessage = { role: "user", content: message };
    set({
      chatHistory: [...get().chatHistory, userMsg],
      isSendingMessage: true,
      error: null
    });

    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/reviews/${jobId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          facts: get().facts
        })
      });

      if (!response.ok) {
        throw new Error("Failed to generate AI response.");
      }

      const data = await response.json();
      const assistantMsg: ChatMessage = { role: "assistant", content: data.reply };
      set({
        chatHistory: [...get().chatHistory, assistantMsg],
        isSendingMessage: false
      });
    } catch (err: any) {
      set({
        chatHistory: [
          ...get().chatHistory,
          { role: "assistant", content: `Sorry, I encountered an error: ${err.message}` }
        ],
        isSendingMessage: false
      });
    }
  },

  submitReview: async (jobId, routerPush) => {
    set({ isResuming: true, error: null });
    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/reviews/${jobId}/facts`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          facts: get().facts
        })
      });

      if (!response.ok) {
        throw new Error("Failed to submit review and resume analysis.");
      }

      set({ isResuming: false });
      // Redirect back to main dashboard
      routerPush();
    } catch (err: any) {
      set({ error: err.message || "Failed to submit review", isResuming: false });
    }
  },

  clearStore: () => {
    set({
      facts: [],
      suggestedQuestions: [],
      chatHistory: [
        {
          role: "assistant",
          content: "Hello! I am your AI RepoProof pairing partner. Feel free to ask me questions about the code, request changes to any claim, or ask me to draft new resume points based on your codebase!"
        }
      ],
      error: null
    });
  }
}));
