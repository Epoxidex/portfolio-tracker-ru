import { Box, Group, Paper, RingProgress, Stack, Text, Title } from "@mantine/core";
import type { PortfolioClassSummary } from "../api/portfolio";
import { formatMoney, formatPercent } from "../lib/format";

const colors = ["indigo.6", "cyan.6", "teal.6", "violet.5", "orange.5", "pink.5"];
export function AllocationPanel({ classes }: { classes: Record<string, PortfolioClassSummary> }) {
  const rows = Object.entries(classes).sort(([,a],[,b])=>b.value-a.value);
  const total = rows.reduce((sum,[,item])=>sum+item.value,0);
  const sections = rows.map(([,item],index)=>({ value: total ? item.value/total*100 : 0, color: colors[index%colors.length] }));
  return (
    <Paper withBorder radius="lg" p="xl" className="feature-card">
      <Group justify="space-between"><div><Text className="section-kicker">Структура</Text><Title order={3}>Классы активов</Title></div><Text size="xs" c="dimmed">{rows.length} классов</Text></Group>
      {rows.length ? <Group align="center" mt="xl" wrap="nowrap" className="allocation-content">
        <RingProgress size={142} thickness={18} roundCaps sections={sections} label={<Text ta="center" size="xs" fw={750}>{formatMoney(total)}</Text>} />
        <Stack gap="sm" style={{flex:1}}>{rows.slice(0,5).map(([name,item],index)=><Group key={name} justify="space-between" wrap="nowrap"><Group gap="xs" wrap="nowrap"><Box w={8} h={8} bg={`var(--mantine-color-${colors[index%colors.length].replace('.', '-')})`} style={{borderRadius:99}}/><div><Text size="xs" fw={700}>{name}</Text><Text size="xs" c="dimmed">{formatPercent(total ? item.value/total : 0,false)}</Text></div></Group><Text size="xs" fw={700}>{formatMoney(item.value)}</Text></Group>)}</Stack>
      </Group> : <Text c="dimmed" ta="center" py={60}>Активов пока нет</Text>}
    </Paper>
  );
}
