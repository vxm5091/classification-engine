import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getVendors,
  createVendor,
  confirmVendor,
  getVendorServices,
  createVendorService,
} from "../api/client";

export function useVendors(search) {
  return useQuery({
    queryKey: ["vendors", search],
    queryFn: () => getVendors(search),
  });
}

export function useVendorServices(vendorId) {
  return useQuery({
    queryKey: ["vendorServices", vendorId],
    queryFn: () => getVendorServices(vendorId),
    enabled: !!vendorId,
  });
}

export function useCreateVendor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createVendor,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vendors"] }),
  });
}

export function useConfirmVendor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => confirmVendor(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vendors"] }),
  });
}

export function useCreateVendorService() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ vendorId, data }) => createVendorService(vendorId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendors"] });
      qc.invalidateQueries({ queryKey: ["vendorServices"] });
    },
  });
}
