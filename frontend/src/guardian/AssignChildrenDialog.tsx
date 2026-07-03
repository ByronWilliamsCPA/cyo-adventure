import { useEffect, useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { useApi } from '../hooks/useApi'
import { AvatarCircle } from '../profiles/AvatarCircle'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import { makeAssignApi } from './assignApi'
import './guardian.css'

interface AssignChildrenDialogProps {
  storybookId: string
  onClose: () => void
  onAssigned?: (profileIds: string[]) => void
}

/**
 * Guardian "Assign more" dialog (wireframe 4.5): a multi-select checklist of
 * family child profiles. Already-assigned children are shown checked and
 * disabled; Save posts only the newly selected ids (add-only, idempotent).
 */
export function AssignChildrenDialog({
  storybookId,
  onClose,
  onAssigned,
}: AssignChildrenDialogProps) {
  const api = useApi()
  const profilesApi = useMemo(() => makeProfilesApi(api), [api])
  const assignApi = useMemo(() => makeAssignApi(api), [api])
  const [profiles, setProfiles] = useState<ProfileView[] | null>(null)
  const [assigned, setAssigned] = useState<Set<string>>(new Set())
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [loadError, setLoadError] = useState(false)
  const [saveError, setSaveError] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [rows, assignedIds] = await Promise.all([
          profilesApi.list(),
          assignApi.get(storybookId),
        ])
        if (!cancelled) {
          setProfiles(rows)
          setAssigned(new Set(assignedIds))
        }
      } catch (err) {
        console.error('assign dialog load failed', err)
        if (!cancelled) setLoadError(true)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [profilesApi, assignApi, storybookId])

  function toggle(id: string) {
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function save() {
    const additions = [...picked].filter((id) => !assigned.has(id))
    if (additions.length === 0) {
      onClose()
      return
    }
    setSaving(true)
    setSaveError(false)
    try {
      const result = await assignApi.add(storybookId, additions)
      onAssigned?.(result)
      onClose()
    } catch (err) {
      console.error('assign save failed', err)
      setSaveError(true)
      setSaving(false)
    }
  }

  const additions = [...picked].filter((id) => !assigned.has(id))

  return (
    <Dialog
      title="Assign to children"
      onClose={onClose}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => void save()}
            disabled={additions.length === 0 || saving}
          >
            Assign
          </Button>
        </>
      }
    >
      {loadError ? (
        <p role="alert">We could not load your family&apos;s profiles.</p>
      ) : profiles === null ? (
        <div role="status" aria-live="polite">
          Loading…
        </div>
      ) : (
        <>
          {saveError ? (
            <p role="alert">We could not assign this story. Please try again.</p>
          ) : null}
          <ul className="assign__list">
            {profiles.map((profile) => {
              const already = assigned.has(profile.id)
              return (
                <li key={profile.id} className="assign__row">
                  <label>
                    <input
                      type="checkbox"
                      checked={already || picked.has(profile.id)}
                      disabled={already}
                      onChange={() => toggle(profile.id)}
                    />
                    <AvatarCircle avatar={profile.avatar} name={profile.display_name} />
                    {profile.display_name}
                  </label>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </Dialog>
  )
}
