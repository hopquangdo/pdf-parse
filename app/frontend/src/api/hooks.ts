import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { JobStatus, JobSummary, Row, UploadOptions } from './types';

const isActive = (s: JobStatus) => s === 'pending' || s === 'running';

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30_000, retry: false });
}

/** Steel/bolt unit weights from the template: static for the life of the server. */
export function useCatalog() {
  return useQuery({ queryKey: ['catalog'], queryFn: api.catalog, staleTime: Infinity });
}

export function useDrawingTypes() {
  return useQuery({ queryKey: ['drawing-types'], queryFn: api.drawingTypes, staleTime: Infinity });
}

/** Drawing extractions and OCR runs together, newest first; polls while anything is still running. */
export function useHistory() {
  return useQuery({
    queryKey: ['jobs'],
    queryFn: api.history,
    refetchInterval: (q) => (q.state.data?.some((j: JobSummary) => isActive(j.status)) ? 2500 : false),
  });
}

export function useOcrJob(id: string) {
  return useQuery({
    queryKey: ['ocr-job', id],
    queryFn: () => api.getOcrJob(id),
    refetchInterval: (q) => (q.state.data && isActive(q.state.data.status) ? 2000 : false),
  });
}

export function useCreateOcrJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, pages, rotate }: { file: File; pages: string; rotate: string | number }) => api.createOcrJob(file, pages, rotate),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  });
}

export function useRetryOcrJob(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.retryOcrJob(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ocr-job', id] }); qc.invalidateQueries({ queryKey: ['jobs'] }); },
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: ['job', id],
    queryFn: () => api.getJob(id),
    refetchInterval: (q) => (q.state.data && isActive(q.state.data.status) ? 2000 : false),
  });
}

export function useUpload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, options }: { file: File; options: UploadOptions }) => api.upload(file, options),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  });
}

export function useSaveRows(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rows: Row[]) => api.saveRows(id, rows),
    onSuccess: (job) => {
      qc.setQueryData(['job', id], job);
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useExport() {
  return useMutation({ mutationFn: ({ rows, paintFactor, jobId }: { rows: Row[]; paintFactor: number; jobId: string }) => api.exportRows(rows, paintFactor, jobId) });
}

// ---- account administration (admins only)
