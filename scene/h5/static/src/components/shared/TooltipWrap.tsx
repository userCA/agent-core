import React from 'react';
import * as Tooltip from '@radix-ui/react-tooltip';

interface Props {
  label: string;
  children: React.ReactElement;
  delayDuration?: number;
}

export default function TooltipWrap({ label, children, delayDuration = 500 }: Props) {
  return (
    <Tooltip.Root delayDuration={delayDuration}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="tooltip-content" sideOffset={6}>
          {label}
          <Tooltip.Arrow className="tooltip-arrow" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
