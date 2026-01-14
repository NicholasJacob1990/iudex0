"use client"

import * as React from "react"
import type { HoverCardContentProps } from "@radix-ui/react-hover-card"

import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export interface RichTooltipProps {
  title: string
  description: string
  badge?: string
  meta?: React.ReactNode
  shortcut?: string
  icon?: React.ReactNode
  side?: HoverCardContentProps["side"]
  align?: HoverCardContentProps["align"]
  sideOffset?: HoverCardContentProps["sideOffset"]
  openDelay?: number
  closeDelay?: number
  contentClassName?: string
  children: React.ReactNode
}

export function RichTooltip({
  title,
  description,
  badge,
  meta,
  shortcut,
  icon,
  side,
  align,
  sideOffset,
  openDelay = 150,
  closeDelay = 100,
  contentClassName,
  children,
}: RichTooltipProps) {
  const hasMeta = Boolean(badge || meta || shortcut)

  return (
    <HoverCard openDelay={openDelay} closeDelay={closeDelay}>
      <HoverCardTrigger asChild>{children}</HoverCardTrigger>
      <HoverCardContent
        side={side}
        align={align}
        sideOffset={sideOffset}
        className={cn("w-80", contentClassName)}
      >
        <div className="flex flex-col gap-2">
          <div className="flex items-start gap-2">
            {icon ? (
              <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 text-primary">
                {icon}
              </div>
            ) : null}
            <div className="space-y-1">
              <h4 className="text-sm font-semibold leading-tight text-foreground">{title}</h4>
              <p className="text-xs text-muted-foreground">{description}</p>
            </div>
          </div>
          {hasMeta ? (
            <div className="flex items-center gap-2 pt-1">
              {badge ? (
                <Badge variant="outline" className="text-[10px] uppercase">
                  {badge}
                </Badge>
              ) : null}
              {meta ? <div className="text-[11px] text-muted-foreground">{meta}</div> : null}
              {shortcut ? (
                <span className="ml-auto text-[11px] text-muted-foreground">{shortcut}</span>
              ) : null}
            </div>
          ) : null}
        </div>
      </HoverCardContent>
    </HoverCard>
  )
}
