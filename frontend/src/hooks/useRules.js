import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getRules, createRule, updateRule, deactivateRule } from "../api/client";

export function useRules() {
  return useQuery({
    queryKey: ["rules"],
    queryFn: getRules,
  });
}

export function useCreateRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createRule,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }),
  });
}

export function useUpdateRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => updateRule(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }),
  });
}

export function useDeactivateRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deactivateRule,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }),
  });
}
