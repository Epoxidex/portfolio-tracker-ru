import { Group, Paper, SimpleGrid, Text, ThemeIcon } from "@mantine/core";
import { IconChartLine, IconCoins, IconPigMoney, IconTrendingUp } from "@tabler/icons-react";
import type { PortfolioSummary } from "../api/portfolio";
import { formatMoney, formatPercent } from "../lib/format";

export function KpiGrid({ summary }: { summary: PortfolioSummary }) {
  const cards = [
    { label: "Стоимость портфеля", value: formatMoney(summary.value), detail: `${formatPercent(summary.pnl_pct)} за всё время`, positive: summary.pnl >= 0, icon: IconCoins, color: "indigo" },
    { label: "Вложено", value: formatMoney(summary.invested), detail: "Только внешние пополнения", icon: IconPigMoney, color: "blue" },
    { label: "Финансовый результат", value: formatMoney(summary.pnl, true), detail: `${formatMoney(summary.income_received)} выплат получено`, positive: summary.pnl >= 0, icon: IconTrendingUp, color: summary.pnl >= 0 ? "teal" : "red" },
    { label: "XIRR", value: summary.xirr === null ? "Нет данных" : formatPercent(summary.xirr), detail: summary.xirr === null ? "Нужна история денежных потоков" : "Годовых с учётом дат", positive: summary.xirr === null ? undefined : summary.xirr >= 0, icon: IconChartLine, color: "violet" },
  ];
  return (
    <SimpleGrid cols={{ base: 1, xs: 2, xl: 4 }} spacing="md">
      {cards.map((card) => (
        <Paper key={card.label} withBorder radius="lg" p="lg" className="metric-card">
          <Group justify="space-between" align="flex-start" wrap="nowrap">
            <div>
              <Text size="xs" c="dimmed" fw={650}>{card.label}</Text>
              <Text className="metric-value" mt="lg">{card.value}</Text>
              <Text size="xs" mt={8} fw={650} c={card.positive === undefined ? "dimmed" : card.positive ? "teal.7" : "red.6"}>{card.detail}</Text>
            </div>
            <ThemeIcon variant="light" color={card.color} radius="md" size={40}><card.icon size={20} stroke={1.8} /></ThemeIcon>
          </Group>
        </Paper>
      ))}
    </SimpleGrid>
  );
}
