import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getTransactions,
  getTransaction,
  approveTransaction,
  reclassifyTransaction,
  flagTransaction,
  convertToRule,
  getStats,
  suggestRules,
  acceptSuggestions,
  reclassifyAll,
  reclassifySingle,
} from "../api/client";

export function useTransactions(params) {
  return useQuery({
    queryKey: ["transactions", params],
    queryFn: () => getTransactions(params),
  });
}

export function useTransaction(id) {
  return useQuery({
    queryKey: ["transaction", id],
    queryFn: () => getTransaction(id),
    enabled: !!id,
  });
}

export function useApproveTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => approveTransaction(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useReclassifyTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => reclassifyTransaction(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useFlagTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => flagTransaction(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useConvertToRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => convertToRule(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rules"] });
    },
  });
}

export function useStats() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: getStats,
  });
}

export function useSuggestRules() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => suggestRules(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useAcceptSuggestions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => acceptSuggestions(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rules"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useReclassifyAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => reclassifyAll(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useReclassifySingle() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (transactionId) => reclassifySingle(transactionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}
