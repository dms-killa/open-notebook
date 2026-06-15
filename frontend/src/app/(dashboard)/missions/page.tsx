'use client'

import { useState } from 'react'
import Link from 'next/link'
import { formatDistanceToNow } from 'date-fns'

import { AppShell } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Plus, RefreshCw } from 'lucide-react'
import { useMissions } from '@/lib/hooks/use-research'
import { CreateMissionDialog } from '@/components/missions/CreateMissionDialog'
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

export default function MissionsPage() {
  const { t } = useTranslation()
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const { data: missions, isLoading, refetch } = useMissions()

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="p-6 space-y-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <h1 className="text-2xl font-bold">{t('missions.title')}</h1>
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
            <Button onClick={() => setCreateDialogOpen(true)}>
              <Plus className="h-4 w-4 mr-2" />
              {t('missions.newMission')}
            </Button>
          </div>

          {isLoading && (
            <div className="text-muted-foreground">{t('common.loading')}</div>
          )}

          {!isLoading && (!missions || missions.length === 0) && (
            <div className="text-center py-12 text-muted-foreground">
              <p className="text-lg font-medium">{t('missions.noMissionsYet')}</p>
              <p className="mt-1">{t('missions.noMissionsDesc')}</p>
              <Button className="mt-4" onClick={() => setCreateDialogOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                {t('missions.newMission')}
              </Button>
            </div>
          )}

          {missions && missions.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {missions.map((mission) => (
                <Link key={mission.id} href={`/missions/${mission.id}`}>
                  <Card className="cursor-pointer hover:shadow-md transition-shadow h-full">
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between gap-2">
                        <CardTitle className="text-base line-clamp-2">
                          {mission.title}
                        </CardTitle>
                        <Badge className={STATUS_COLORS[mission.status]} variant="outline">
                          {t(`missions.status.${mission.status}`)}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <p className="text-sm text-muted-foreground line-clamp-2">
                        {mission.query}
                      </p>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Badge variant="secondary" className="text-xs">
                          {t(`missions.depth.${mission.depth}`)}
                        </Badge>
                        {mission.created && (
                          <span>
                            {formatDistanceToNow(new Date(mission.created), { addSuffix: true })}
                          </span>
                        )}
                      </div>
                      <Progress value={mission.progress} className="h-1.5" />
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      <CreateMissionDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
      />
    </AppShell>
  )
}
