import { Paper, SimpleGrid, Text } from "@mantine/core";
import type { ReturnDelta } from "../api/dashboard";
import { formatMoney, formatPercent } from "../lib/format";

export function PerformanceStrip({ values }: { values: Array<{ label: string; delta?: ReturnDelta }> }) {
  return (
    <Paper className="performance-card" radius="lg" p={6}>
      <SimpleGrid cols={{ base: 2, md: 4 }} spacing={0}>
        {values.map(({ label, delta }) => {
          const available = delta?.change != null && delta.pct != null;
          const positive = (delta?.change ?? 0) >= 0;
          return <div className="performance-cell" key={label}><Text size="xs" c="gray.5">{label}</Text><Text fw={760} size="lg" mt={5} c={available ? positive ? "teal.3" : "red.3" : "white"}>{available ? formatMoney(delta.change!, true) : "—"}</Text><Text size="xs" c={available ? positive ? "teal.4" : "red.4" : "gray.6"}>{available ? formatPercent(delta.pct!) : "нет опорного снимка"}</Text></div>;
        })}
      </SimpleGrid>
    </Paper>
  );
}
