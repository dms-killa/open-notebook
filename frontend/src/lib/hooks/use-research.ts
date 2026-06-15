import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { researchApi } from '@/lib/api/research'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorKey } from '@/lib/utils/error-handler'
import { CreateMissionRequest } from '@/lib/types/research'

export function useMissions() {
  return useQuery({
    queryKey: QUERY_KEYS.missions,
    queryFn: () => researchApi.list(),
  })
}

export function useMission(id: string) {
  return useQuery({
    queryKey: QUERY_KEYS.mission(id),
    queryFn: () => researchApi.get(id),
    enabled: !!id,
  })
}

export function useMissionNotes(id: string) {
  return useQuery({
    queryKey: QUERY_KEYS.missionNotes(id),
    queryFn: () => researchApi.getNotes(id),
    enabled: !!id,
  })
}

export function useCreateMission() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: CreateMissionRequest) => researchApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.missions })
      toast({
        title: t('common.success'),
        description: t('missions.createSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: t(getApiErrorKey(error, t('common.error'))),
        variant: 'destructive',
      })
    },
  })
}

export function useStartMission() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (id: string) => researchApi.start(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.missions })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.mission(id) })
      toast({
        title: t('common.success'),
        description: t('missions.startSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: t(getApiErrorKey(error, t('common.error'))),
        variant: 'destructive',
      })
    },
  })
}

export function useDeleteMission() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (id: string) => researchApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.missions })
      toast({
        title: t('common.success'),
        description: t('missions.deleteSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: t(getApiErrorKey(error, t('common.error'))),
        variant: 'destructive',
      })
    },
  })
}
