import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getTransactions,
  getTransaction,
  approveTransaction,
  reclassifyTransaction,
  flagTransaction,
  convertToRule,
  getStats,
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
