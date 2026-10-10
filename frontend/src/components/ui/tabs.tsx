import { Tabs as TabsPrimitive } from "@base-ui/react/tabs"
import { cn } from "@/lib/utils"

function Tabs({ className, ...props }: TabsPrimitive.Root.Props) {
  return <TabsPrimitive.Root data-slot="tabs" className={cn("flex flex-col gap-6", className)} {...props} />
}

function TabsList({ className, ...props }: TabsPrimitive.List.Props) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn("inline-flex w-fit max-w-full items-center gap-1 overflow-x-auto rounded-2xl border border-border bg-background p-1 shadow-xs", className)}
      {...props}
    />
  )
}

function TabsTrigger({ className, ...props }: TabsPrimitive.Tab.Props) {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      className={cn(
        "inline-flex h-9 shrink-0 items-center gap-2 rounded-xl px-2.5 text-sm font-medium sm:px-3.5 whitespace-nowrap text-muted-foreground transition-colors outline-none select-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 data-[active]:bg-accent data-[active]:text-accent-foreground [&_svg]:hidden [&_svg]:size-4 [&_svg]:shrink-0 sm:[&_svg]:block",
        className
      )}
      {...props}
    />
  )
}

function TabsContent({ className, ...props }: TabsPrimitive.Panel.Props) {
  return <TabsPrimitive.Panel data-slot="tabs-content" className={cn("flex flex-col gap-6 outline-none", className)} {...props} />
}

export { Tabs, TabsList, TabsTrigger, TabsContent }
