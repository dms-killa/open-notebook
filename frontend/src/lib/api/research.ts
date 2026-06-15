import apiClient from './client'
import { getApiUrl } from '@/lib/config'
import {
  ResearchMission,
  ResearchNote,
  CreateMissionRequest,
} from '@/lib/types/research'

export const researchApi = {
  list: async () => {
    const response = await apiClient.get<ResearchMission[]>('/missions')
    return response.data
  },

  get: async (id: string) => {
    const response = await apiClient.get<ResearchMission>(`/missions/${id}`)
    return response.data
  },

  create: async (data: CreateMissionRequest) => {
    const response = await apiClient.post<ResearchMission>('/missions', data)
    return response.data
  },

  start: async (id: string) => {
    const response = await apiClient.post<ResearchMission>(`/missions/${id}/start`)
    return response.data
  },

  delete: async (id: string) => {
    const response = await apiClient.delete(`/missions/${id}`)
    return response.data
  },

  getNotes: async (id: string) => {
    const response = await apiClient.get<ResearchNote[]>(`/missions/${id}/notes`)
    return response.data
  },

  streamProgressUrl: async (id: string) => {
    const apiUrl = await getApiUrl()
    return `${apiUrl}/api/missions/${id}/stream`
  },
}
