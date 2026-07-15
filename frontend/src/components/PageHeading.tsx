import { Box, Group, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

export function PageHeading({ eyebrow, title, subtitle, actions }: { eyebrow: string; title: string; subtitle: string; actions?: ReactNode }) {
  return (
    <Group className="page-heading" justify="space-between" align="flex-end" wrap="wrap">
      <Box>
        <Text className="eyebrow">{eyebrow}</Text>
        <Title order={1}>{title}</Title>
        <Text className="subtitle">{subtitle}</Text>
      </Box>
      {actions && <Group>{actions}</Group>}
    </Group>
  );
}
