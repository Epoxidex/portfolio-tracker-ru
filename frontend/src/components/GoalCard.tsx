import { Badge, Group, Paper, Progress, Stack, Text, Title } from "@mantine/core";
import { IconFlame } from "@tabler/icons-react";
import { formatMoney } from "../lib/format";

export function GoalCard({ current, goal, streak }: { current: number; goal: number; streak: number }) {
  const progress = Math.min(100, Math.max(0, current / Math.max(goal, 1) * 100));
  return (
    <Paper withBorder radius="lg" p="xl" className="feature-card">
      <Group justify="space-between" align="flex-start">
        <div><Text className="section-kicker">Большая цель</Text><Title order={3}>{formatMoney(goal)}</Title></div>
        <Badge variant="light" color="orange" leftSection={<IconFlame size={13} />}>{streak} дн.</Badge>
      </Group>
      <Stack gap="xs" mt={48}>
        <Group justify="space-between" align="flex-end"><Text className="goal-percent">{progress.toFixed(1)}%</Text><Text size="xs" c="dimmed">Осталось {formatMoney(Math.max(0, goal-current))}</Text></Group>
        <Progress value={progress} size="lg" radius="xl" color="indigo" />
        <Text size="xs" c="dimmed" mt="xs">Сейчас накоплено {formatMoney(current)}. Цель берётся из локальной настройки портфеля.</Text>
      </Stack>
    </Paper>
  );
}
