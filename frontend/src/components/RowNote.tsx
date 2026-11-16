import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Flag, Info } from 'lucide-react'
import { cn } from '../lib/utils'

/**
 * A row's notes behind one small button beside its name, for tables and
 * lists. "attention" marks a note that questions a figure (very high for the
 * institution's size, an unusual year); "info" one that explains it.
 */
export type RowNoteKind = 'info' | 'attention'

export interface RowNoteItem {
  kind: RowNoteKind
  text: string
}

// Layout effects run only in the browser; the prerender uses plain effects
const useBrowserLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

const GAP = 6 // between the button and the popover
const EDGE = 8 // kept free at the window's edges
const WIDTH = 320 // the popover's width where there is room
const HOVER_DELAY = 150 // ms before a popover left by the pointer closes

// One popover open at a time: a note that opens tells the others
const OPEN_EVENT = 'rownote:open'

/**
 * The popover opens on mouse hover and on keyboard focus, and a click or tap
 * toggles it; Escape closes it. It is drawn in a layer of its own at the
 * button (fixed position, flipped above when there is no room below), so a
 * table's scroll container does not clip it and the row does not move.
 * Screen readers get the notes as the button's description.
 */
export default function RowNote({
  subject, notes, className,
}: {
  // What the notes are about, for the button's name ("Note about {subject}")
  subject: string
  notes: RowNoteItem[]
  className?: string
}) {
  const id = useId()
  const descId = `${id}-text`
  const buttonRef = useRef<HTMLButtonElement>(null)
  const popRef = useRef<HTMLDivElement>(null)
  const timer = useRef<number | null>(null)
  const [hover, setHover] = useState(false)
  const [keyboardFocus, setKeyboardFocus] = useState(false)
  const [pinned, setPinned] = useState(false)
  // Closed by a click or Escape while hover or focus would keep it open;
  // cleared when both are gone
  const [dismissed, setDismissed] = useState(false)
  const open = notes.length > 0 && !dismissed && (pinned || hover || keyboardFocus)
  const attention = notes.some((n) => n.kind === 'attention')

  const clearTimer = () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = null
  }
  const enter = (e: React.PointerEvent) => {
    if (e.pointerType !== 'mouse') return
    clearTimer()
    setHover(true)
  }
  const leave = (e: React.PointerEvent) => {
    if (e.pointerType !== 'mouse') return
    clearTimer()
    timer.current = window.setTimeout(() => setHover(false), HOVER_DELAY)
  }
  useEffect(() => clearTimer, [])

  useEffect(() => {
    if (dismissed && !hover && !keyboardFocus) setDismissed(false)
  }, [dismissed, hover, keyboardFocus])

  // Place the popover at the button: below, or above when only there is
  // room, kept inside the window
  const place = useCallback(() => {
    const button = buttonRef.current
    const pop = popRef.current
    if (!button || !pop) return
    const r = button.getBoundingClientRect()
    const vw = document.documentElement.clientWidth
    const vh = window.innerHeight
    const width = Math.min(WIDTH, vw - 2 * EDGE)
    pop.style.width = `${width}px`
    pop.style.maxHeight = `${vh - 2 * EDGE}px`
    const h = pop.offsetHeight
    const below = vh - r.bottom - GAP - EDGE
    const above = r.top - GAP - EDGE
    let top = h <= below || below >= above ? r.bottom + GAP : r.top - GAP - h
    top = Math.max(EDGE, Math.min(top, vh - EDGE - h))
    const left = Math.max(EDGE, Math.min(r.left + r.width / 2 - width / 2, vw - EDGE - width))
    pop.style.top = `${top}px`
    pop.style.left = `${left}px`
    pop.style.visibility = 'visible'
  }, [])

  useBrowserLayoutEffect(() => {
    if (open) place()
  }, [open, place, notes])

  // While open: follow the button on scroll and resize (a pinned note
  // closes when its button leaves the window), close on Escape and on a
  // press outside, and close when another note opens
  useEffect(() => {
    if (!open) return
    window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: id }))
    const onScroll = () => {
      const r = buttonRef.current?.getBoundingClientRect()
      if (r && (r.bottom < 0 || r.top > window.innerHeight)) {
        setPinned(false)
        setHover(false)
      }
      place()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      const button = buttonRef.current
      const hadFocus = document.activeElement === button
      setDismissed(true)
      setPinned(false)
      // Back to the button when the note was opened from it (not by hover alone)
      if (button && (pinned || hadFocus)) button.focus({ preventScroll: true })
    }
    const onPress = (e: PointerEvent) => {
      const t = e.target as Node
      if (buttonRef.current?.contains(t) || popRef.current?.contains(t)) return
      setPinned(false)
    }
    const onOther = (e: Event) => {
      if ((e as CustomEvent<string>).detail === id) return
      setPinned(false)
      setHover(false)
      setDismissed(true)
    }
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', place)
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPress)
    window.addEventListener(OPEN_EVENT, onOther)
    return () => {
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', place)
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPress)
      window.removeEventListener(OPEN_EVENT, onOther)
    }
  }, [open, pinned, id, place])

  if (notes.length === 0) return null
  const Icon = attention ? Flag : Info
  const label = `${notes.length === 1 ? 'Note' : 'Notes'} about ${subject}`

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-label={label}
        aria-describedby={descId}
        onClick={() => {
          if (open) {
            setPinned(false)
            setDismissed(true)
          } else {
            setPinned(true)
            setDismissed(false)
          }
        }}
        onFocus={(e) => {
          let visible = true
          try {
            visible = e.currentTarget.matches(':focus-visible')
          } catch {
            // A browser without :focus-visible: treat focus as from the keyboard
          }
          setKeyboardFocus(visible)
        }}
        onBlur={() => {
          setKeyboardFocus(false)
          setPinned(false)
        }}
        onPointerEnter={enter}
        onPointerLeave={leave}
        className={cn(
          'relative inline-flex items-center justify-center w-6 h-6 -my-1 align-middle rounded flex-shrink-0',
          attention ? 'text-attention' : 'text-ink-3',
          'hover:bg-tint',
          open && 'bg-tint',
          className
        )}
      >
        <Icon className="w-4 h-4" aria-hidden="true" />
      </button>
      {/* The notes as the button's description (read by screen readers, not shown) */}
      <span id={descId} hidden>
        {notes.map((n) => n.text).join(' ')}
      </span>
      {open && typeof document !== 'undefined' && createPortal(
        <div
          ref={popRef}
          // The button's description already gives these notes to screen readers
          aria-hidden="true"
          onPointerEnter={enter}
          onPointerLeave={leave}
          style={{ position: 'fixed', top: 0, left: 0, visibility: 'hidden' }}
          className="z-[70] overflow-y-auto rounded border border-rule-strong/60 bg-surface p-3 text-meta text-ink-2 shadow-pop"
        >
          {notes.length === 1 ? (
            <NoteLine item={notes[0]} />
          ) : (
            <ul className="space-y-2">
              {notes.map((n) => (
                <li key={n.text}><NoteLine item={n} /></li>
              ))}
            </ul>
          )}
        </div>,
        document.body
      )}
    </>
  )
}

function NoteLine({ item }: { item: RowNoteItem }) {
  const Icon = item.kind === 'attention' ? Flag : Info
  return (
    <p className="flex items-start gap-1.5">
      <Icon
        className={cn(
          'w-3.5 h-3.5 mt-0.5 flex-shrink-0',
          item.kind === 'attention' ? 'text-attention' : 'text-ink-3'
        )}
        aria-hidden="true"
      />
      <span>{item.text}</span>
    </p>
  )
}
