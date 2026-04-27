import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export const useStore = create(
  persist(
    (set, get) => ({
      // ── Authentication ──────────────────────────────────────────────────
      isAuthenticated: false,
      rememberedUsername: '',
      login: (username = '', remember = false) =>
        set({
          isAuthenticated: true,
          rememberedUsername: remember ? username : '',
        }),
      logout: () =>
        set({
          isAuthenticated: false,
          rememberedUsername: '',
          portfolioId: null,
          holdings: [],
          portfolioValue: 0,
          analyticsData: null,
          optimizationData: null,
          alerts: [],
          advisoryProgress: null,
        }),

      // ── Portfolio ───────────────────────────────────────────────────────
      portfolioId: null,

      analyticsData: null,
      optimizationData: null,

      portfolioValue: 0,
      dayReturn: 0,
      dayReturnPercent: 0,
      overallReturn: 0,
      overallReturnPercent: 0,
      holdings: [],

      setAnalytics: (data) => {
        const summary = data?.portfolio_summary || {};
        const weights = data?.current_weights || {};
        const returnsMap = data?.absolute_returns || {};

        const holdings = Object.entries(returnsMap).map(([symbol, r], idx) => ({
          id: idx,
          symbol,
          name: symbol,
          allocation: weights[symbol] != null ? parseFloat((weights[symbol] * 100).toFixed(2)) : 0,
          value: r?.market_value ?? 0,
          return: r?.percentage_return ?? 0,
          avgBuyPrice: r?.average_buy_price ?? 0,
          currentPrice: r?.current_price ?? 0,
          absoluteReturnInr: r?.absolute_return_inr ?? 0,
        }));

        set({
          analyticsData: data,
          portfolioValue: data?.total_portfolio_value ?? 0,
          overallReturn: summary?.total_absolute_return_inr ?? 0,
          overallReturnPercent: summary?.total_percentage_return ?? 0,
          dayReturn: 0,
          dayReturnPercent: 0,
          holdings,
        });
      },
      setOptimization: (data) => set({ optimizationData: data }),

      // ── Alerts ──────────────────────────────────────────────────────────
      alerts: [],
      // Live progress while an advisory is being generated
      // { step: string, message: string } | null
      advisoryProgress: null,

      setAlertStatus: (id, status) =>
        set((state) => ({
          alerts: state.alerts.map((a) => (a.id === id ? { ...a, status } : a)),
        })),

      setAdvisoryProgress: (progress) => set({ advisoryProgress: progress }),

      // ── WebSockets ──────────────────────────────────────────────────────
      ws: null,
      connectWebSocket: (portfolioId) => {
        const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${wsProto}//${window.location.host}/api/v1/ws/${portfolioId}`);

        ws.onopen = () => console.log('Connected to Equisight Alert Stream.');
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            if (data.type === 'advisory_progress') {
              // Show live status — clear when recommendation arrives
              set({ advisoryProgress: { step: data.step, message: data.message } });
            } else if (data.type === 'new_recommendation') {
              // Advisory is ready — clear progress card and add alert
              set((state) => ({
                advisoryProgress: null,
                alerts: [
                  {
                    id: data.recommendation_id,
                    title: `${data.action} Recommended`,
                    explanation: data.explanation,
                    scenario: {
                      currentRisk: 'High Unintended Risk',
                      projectedRisk: 'Risk-Aligned',
                      details: data.scenario_projection,
                    },
                    proposedWeights: data.proposed_weights,
                    ragSources: data.rag_sources,
                    status: 'pending',
                    timestamp: Date.now(),
                  },
                  ...state.alerts,
                ],
              }));
            }
          } catch (err) {
            console.error('Failed to parse WS message:', err);
          }
        };
        ws.onclose = () => {
          console.log('Disconnected from Alert Stream.');
          // Clear in-flight progress if socket drops
          set({ advisoryProgress: null });
        };
        set({ ws });
      },

      setPortfolioId: (id) =>
        set((state) => {
          if (state.ws) state.ws.close();
          setTimeout(() => get().connectWebSocket(id), 0);
          return { portfolioId: id };
        }),
    }),
    {
      name: 'equisight-session',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        isAuthenticated: state.isAuthenticated,
        rememberedUsername: state.rememberedUsername,
        portfolioId: state.portfolioId,
        holdings: state.holdings,
        portfolioValue: state.portfolioValue,
        overallReturn: state.overallReturn,
        overallReturnPercent: state.overallReturnPercent,
        alerts: state.alerts,
        analyticsData: state.analyticsData,
        optimizationData: state.optimizationData,
        // advisoryProgress intentionally NOT persisted — it's transient
      }),
    }
  )
);
