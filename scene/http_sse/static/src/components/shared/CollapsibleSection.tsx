import * as Collapsible from '@radix-ui/react-collapsible';
import React from 'react';

interface CollapsibleSectionProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trigger: React.ReactElement;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
}

export default function CollapsibleSection({
  open,
  onOpenChange,
  trigger,
  children,
  className = '',
  contentClassName = '',
}: CollapsibleSectionProps) {
  return (
    <Collapsible.Root open={open} onOpenChange={onOpenChange} className={className}>
      <Collapsible.Trigger asChild>
        {trigger}
      </Collapsible.Trigger>
      <Collapsible.Content className={`collapsible-content ${contentClassName}`.trim()}>
        {children}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
