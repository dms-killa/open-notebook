'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useCreateMission } from '@/lib/hooks/use-research'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { useTranslation } from '@/lib/hooks/use-translation'

const createMissionSchema = z.object({
  query: z.string().min(1, 'Query is required'),
  title: z.string().optional(),
  depth: z.enum(['quick', 'comprehensive', 'exhaustive']).default('comprehensive'),
  notebook_id: z.string().optional(),
})

type CreateMissionFormData = z.infer<typeof createMissionSchema>

interface CreateMissionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateMissionDialog({ open, onOpenChange }: CreateMissionDialogProps) {
  const { t } = useTranslation()
  const router = useRouter()
  const createMission = useCreateMission()
  const { data: notebooks } = useNotebooks(false)
  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
    reset,
    setValue,
    watch,
  } = useForm<CreateMissionFormData>({
    resolver: zodResolver(createMissionSchema),
    mode: 'onChange',
    defaultValues: {
      query: '',
      title: '',
      depth: 'comprehensive',
      notebook_id: '',
    },
  })

  const closeDialog = () => onOpenChange(false)

  const onSubmit = async (data: CreateMissionFormData) => {
    const payload = {
      ...data,
      notebook_id: data.notebook_id || undefined,
      title: data.title || undefined,
    }
    const mission = await createMission.mutateAsync(payload)
    closeDialog()
    reset()
    router.push(`/missions/${mission.id}`)
  }

  useEffect(() => {
    if (!open) {
      reset()
    }
  }, [open, reset])

  const depthValue = watch('depth')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[540px]">
        <DialogHeader>
          <DialogTitle>{t('missions.createNew')}</DialogTitle>
          <DialogDescription>
            {t('missions.createNewDesc')}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="mission-query">{t('missions.queryLabel')} *</Label>
            <Textarea
              id="mission-query"
              {...register('query')}
              placeholder={t('missions.queryPlaceholder')}
              rows={4}
            />
            {errors.query && (
              <p className="text-sm text-destructive">{errors.query.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="mission-title">{t('common.title')} ({t('common.optional')})</Label>
            <Input
              id="mission-title"
              {...register('title')}
              placeholder={t('missions.titlePlaceholder')}
              autoComplete="off"
            />
          </div>

          <div className="space-y-2">
            <Label>{t('missions.depthLabel')}</Label>
            <Select
              value={depthValue}
              onValueChange={(value) => setValue('depth', value as CreateMissionFormData['depth'])}
            >
              <SelectTrigger>
                <SelectValue placeholder={t('missions.depthPlaceholder')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="quick">{t('missions.depth.quick')}</SelectItem>
                <SelectItem value="comprehensive">{t('missions.depth.comprehensive')}</SelectItem>
                <SelectItem value="exhaustive">{t('missions.depth.exhaustive')}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {notebooks && notebooks.length > 0 && (
            <div className="space-y-2">
              <Label>{t('common.notebook')} ({t('common.optional')})</Label>
              <Select
                value={watch('notebook_id') || ''}
                onValueChange={(value) => setValue('notebook_id', value === 'none' ? '' : value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t('missions.selectNotebook')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">{t('missions.noNotebook')}</SelectItem>
                  {notebooks.map((nb) => (
                    <SelectItem key={nb.id} value={nb.id}>
                      {nb.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={closeDialog}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={!isValid || createMission.isPending}>
              {createMission.isPending ? t('common.creating') : t('missions.createNew')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
