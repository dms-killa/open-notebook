'use client'

import { useEffect, useRef, useCallback, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { formatDistanceToNow } from 'date-fns'

import { AppShell } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ArrowLeft, Play, Trash2 } from 'lucide-react'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { useMission, useMissionNotes, useStartMission, useDeleteMission } from '@/lib/hooks/use-research'
import { researchApi } from '@/lib/api/research'
import { useQueryClient } from '@tanstack/react-query'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { ResearchMission } from '@/lib/types/research'

const STATUS_COLORS: Record<ResearchMission['status'], string> = {
  planning: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  researching: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  reflecting: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
  writing: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
  completed: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  paused: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
}

const RUNNING_STATUSES: ResearchMission['status'][] = ['researching', 'reflecting', 'writing']

export default function MissionDetailPage() {
  const { t } = useTranslation()
  const params = useParams()
  const router = useRouter()
  const queryClient = useQueryClient()
  const id = params.id as string

  const { data: mission, isLoading } = useMission(id)
  const { data: notes } = useMissionNotes(id)
  const startMission = useStartMission()
  const deleteMission = useDeleteMission()

  const eventSourceRef = useRef<EventSource | null>(null)
  const [sseConnected, setSseConnected] = useState(false)

  const isRunning = mission && RUNNING_STATUSES.includes(mission.status)

  const connectSSE = useCallback(async () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const url = await researchApi.streamProgressUrl(id)
    const authStorage = typeof window !== 'undefined' ? localStorage.getItem('auth-storage') : null
    let token = ''
    if (authStorage) {
      try {
        const { state } = JSON.parse(authStorage)
        token = state?.token || ''
      } catch {
        // ignore
      }
    }

    const streamUrl = token ? `${url}?token=${encodeURIComponent(token)}` : url
    const es = new EventSource(streamUrl)
    eventSourceRef.current = es

    es.onopen = () => setSseConnected(true)

    es.onmessage = () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.mission(id) })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.missionNotes(id) })
    }

    es.onerror = () => {
      setSseConnected(false)
      es.close()
      eventSourceRef.current = null
    }
  }, [id, queryClient])

  useEffect(() => {
    if (isRunning && !sseConnected) {
      connectSSE()
    }

    if (!isRunning && eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
      setSseConnected(false)
    }

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
    }
  }, [isRunning, sseConnected, connectSSE])

  const handleStart = async () => {
    await startMission.mutateAsync(id)
  }

  const handleDelete = async () => {
    await deleteMission.mutateAsync(id)
    router.push('/missions')
  }

  // Group notes by phase
  const notesByPhase = notes?.reduce<Record<string, typeof notes>>((acc, note) => {
    const phase = note.phase || 'unknown'
    if (!acc[phase]) acc[phase] = []
    acc[phase].push(note)
    return acc
  }, {}) ?? {}

  if (isLoading) {
    return (
      <AppShell>
        <div className="flex-1 flex items-center justify-center">
          <p className="text-muted-foreground">{t('common.loading')}</p>
        </div>
      </AppShell>
    )
  }

  if (!mission) {
    return (
      <AppShell>
        <div className="flex-1 flex items-center justify-center">
          <p className="text-muted-foreground">{t('missions.notFound')}</p>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="p-6 space-y-6">
          {/* Header */}
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-2">
              <Button variant="ghost" size="sm" onClick={() => router.push('/missions')}>
                <ArrowLeft className="h-4 w-4 mr-1" />
                {t('common.back')}
              </Button>
              <h1 className="text-2xl font-bold">{mission.title}</h1>
              <p className="text-muted-foreground">{mission.query}</p>
              <div className="flex items-center gap-3">
                <Badge className={STATUS_COLORS[mission.status]} variant="outline">
                  {t(`missions.status.${mission.status}`)}
                </Badge>
                <Badge variant="secondary">
                  {t(`missions.depth.${mission.depth}`)}
                </Badge>
                {mission.created && (
                  <span className="text-sm text-muted-foreground">
                    {formatDistanceToNow(new Date(mission.created), { addSuffix: true })}
                  </span>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              {mission.status === 'planning' && (
                <Button onClick={handleStart} disabled={startMission.isPending}>
                  <Play className="h-4 w-4 mr-2" />
                  {startMission.isPending ? t('common.processing') : t('missions.startResearch')}
                </Button>
              )}

              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive" size="sm">
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>{t('missions.deleteMission')}</AlertDialogTitle>
                    <AlertDialogDescription>
                      {t('missions.deleteConfirm')}
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                    <AlertDialogAction onClick={handleDelete}>
                      {t('common.delete')}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>

          {/* Progress bar */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">{t('common.progress')}</span>
              <span className="font-medium">{mission.progress}%</span>
            </div>
            <Progress value={mission.progress} className="h-2" />
          </div>

          {/* Error message */}
          {mission.error_message && (
            <div className="rounded-md bg-destructive/10 border border-destructive/20 p-4 text-sm text-destructive">
              {mission.error_message}
            </div>
          )}

          {/* Tabs */}
          <Tabs defaultValue="report" className="w-full">
            <TabsList>
              <TabsTrigger value="report">{t('missions.tabs.report')}</TabsTrigger>
              <TabsTrigger value="notes">{t('missions.tabs.notes')}</TabsTrigger>
              <TabsTrigger value="activity">{t('missions.tabs.activity')}</TabsTrigger>
            </TabsList>

            {/* Report Tab */}
            <TabsContent value="report" className="mt-4">
              {mission.report ? (
                <Card>
                  <CardContent className="pt-6 prose dark:prose-invert max-w-none">
                    <div dangerouslySetInnerHTML={{ __html: mission.report }} />
                  </CardContent>
                </Card>
              ) : (
                <div className="text-center py-12 text-muted-foreground">
                  <p>{t('missions.reportNotReady')}</p>
                </div>
              )}
            </TabsContent>

            {/* Notes Tab */}
            <TabsContent value="notes" className="mt-4 space-y-6">
              {Object.keys(notesByPhase).length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <p>{t('missions.noNotesYet')}</p>
                </div>
              ) : (
                Object.entries(notesByPhase).map(([phase, phaseNotes]) => (
                  <div key={phase} className="space-y-3">
                    <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                      {phase}
                    </h3>
                    <div className="space-y-2">
                      {phaseNotes.map((note) => (
                        <Card key={note.id}>
                          <CardContent className="pt-4 space-y-2">
                            <p className="text-sm">{note.content}</p>
                            {note.source_url && (
                              <a
                                href={note.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs text-primary hover:underline"
                              >
                                {note.source_url}
                              </a>
                            )}
                            {note.source_type && (
                              <Badge variant="secondary" className="text-xs">
                                {note.source_type}
                              </Badge>
                            )}
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </TabsContent>

            {/* Activity Log Tab */}
            <TabsContent value="activity" className="mt-4">
              {!mission.execution_log || mission.execution_log.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <p>{t('missions.noActivityYet')}</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {mission.execution_log.map((entry, index) => (
                    <div
                      key={index}
                      className="flex gap-4 border-l-2 border-muted pl-4 py-2"
                    >
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-xs">
                            {entry.phase}
                          </Badge>
                          <span className="text-xs text-muted-foreground font-medium">
                            {entry.agent}
                          </span>
                          {entry.timestamp && (
                            <span className="text-xs text-muted-foreground">
                              {formatDistanceToNow(new Date(entry.timestamp), { addSuffix: true })}
                            </span>
                          )}
                        </div>
                        <p className="text-sm">{entry.message}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </AppShell>
  )
}
