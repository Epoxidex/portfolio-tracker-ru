import { useEffect, useMemo, useState } from "react";
import { BarChart, LineChart } from "@mantine/charts";
import { Badge, Group, Paper, SegmentedControl, Select, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { getHistory,getLeaders,getPriceHistory,getReturns,type HistoryPoint,type Leader,type PriceSeries,type ReturnPoint } from "../api/dashboard";
import { PageHeading } from "../components/PageHeading";
import { formatMoney,formatPercent } from "../lib/format";

export function AnalyticsPage({revision}:{revision:number}) {
  const [history,setHistory]=useState<HistoryPoint[]>([]),[returns,setReturns]=useState<ReturnPoint[]>([]),[leaders,setLeaders]=useState<Leader[]>([]),[series,setSeries]=useState<PriceSeries[]>([]);
  const [returnPeriod,setReturnPeriod]=useState<"daily"|"monthly"|"yearly">("monthly"),[valuePeriod,setValuePeriod]=useState<"day"|"week"|"month">("day"),[leaderPeriod,setLeaderPeriod]=useState<"day"|"week"|"month">("month"),[priceId,setPriceId]=useState<string|null>(null),[priceDays,setPriceDays]=useState("365");
  useEffect(()=>{void getHistory().then(setHistory)},[revision]);
  useEffect(()=>{void getPriceHistory(Number(priceDays)).then(items=>{setSeries(items);setPriceId(current=>current??String(items[0]?.id??""))})},[priceDays,revision]);
  useEffect(()=>{void getReturns(returnPeriod).then(data=>setReturns(data.points))},[returnPeriod,revision]);
  useEffect(()=>{void getLeaders(leaderPeriod).then(data=>setLeaders(data.items))},[leaderPeriod,revision]);
  const selected=useMemo(()=>series.find(item=>String(item.id)===priceId),[series,priceId]); const valueHistory=useMemo(()=>bucketHistory(history,valuePeriod),[history,valuePeriod]);
  const valueData=valueHistory.map(item=>({date:item.day||item.ts.slice(0,10),value:item.value,invested:item.invested})); const returnData=returns.map(item=>({period:item.label,return:item.pct*100})); const priceData=(selected?.history??[]).map(item=>({date:item.ts.slice(0,10),price:item.price}));
  return <><PageHeading eyebrow="Динамика" title="Аналитика" subtitle="Стоимость, доходность и вклад каждого актива — без декоративного шума"/>
    <SimpleGrid cols={{base:1,xl:2}} spacing="md">
      <ChartCard kicker="По снимкам" title="Стоимость портфеля" control={<SegmentedControl size="xs" value={valuePeriod} onChange={v=>setValuePeriod(v as typeof valuePeriod)} data={[{label:"Дни",value:"day"},{label:"Недели",value:"week"},{label:"Месяцы",value:"month"}]}/>}>
        {valueData.length?<LineChart h={330} data={valueData} dataKey="date" curveType="natural" series={[{name:"value",label:"Стоимость",color:"indigo.6"},{name:"invested",label:"Внешние пополнения",color:"gray.5"}]} valueFormatter={value=>formatMoney(value)} withLegend gridAxis="y"/>:<Empty text="График появится после первого снимка"/>}
      </ChartCard>
      <ChartCard kicker="Результат по периодам" title="Доходность" control={<SegmentedControl size="xs" value={returnPeriod} onChange={v=>setReturnPeriod(v as typeof returnPeriod)} data={[{label:"Дни",value:"daily"},{label:"Месяцы",value:"monthly"},{label:"Годы",value:"yearly"}]}/>}>
        {returnData.length?<BarChart h={330} data={returnData} dataKey="period" series={[{name:"return",label:"Доходность, %",color:"gray.6"}]} getBarColor={returnBarColor} valueFormatter={v=>`${v.toFixed(2)}%`} referenceLines={[{y:0,color:"gray.5"}]} gridAxis="y"/>:<Empty text="Нужно минимум два снимка"/>}
      </ChartCard>
      <Paper withBorder radius="lg" p="xl">
        <Group justify="space-between" align="flex-start"><div><Text className="section-kicker">Вклад в изменение</Text><Title order={3}>Лидеры движения</Title></div><SegmentedControl size="xs" value={leaderPeriod} onChange={v=>setLeaderPeriod(v as typeof leaderPeriod)} data={[{label:"День",value:"day"},{label:"Неделя",value:"week"},{label:"Месяц",value:"month"}]}/></Group>
        <Stack gap={0} mt="lg">{leaders.length?leaders.slice().sort((a,b)=>Math.abs(b.change)-Math.abs(a.change)).map((item,index)=><Group className="leader-row" key={`${item.name}-${index}`} justify="space-between" wrap="nowrap"><Group wrap="nowrap"><div className="rank-chip">{index+1}</div><div><Text size="sm" fw={750}>{item.ticker||item.name}</Text><Text size="xs" c="dimmed">{item.ticker?item.name:""}</Text></div></Group><Group gap="xl" wrap="nowrap"><div className="leader-value"><Text size="sm" fw={700}>{formatMoney(item.value)}</Text><Text size="xs" c="dimmed">{item.change_pct===null?"новая позиция":formatPercent(item.change_pct)}</Text></div><div className="leader-value"><Text size="sm" fw={750} c={item.change>=0?"teal.7":"red.6"}>{formatMoney(item.change,true)}</Text><Badge size="xs" variant="light" color={item.change>=0?"teal":"red"}>{formatPercent(item.impact_pct,false)} движения</Badge></div></Group></Group>):<Empty text="Нет изменений за выбранный период"/>}</Stack>
      </Paper>
      <ChartCard kicker="Рынок" title="История цены" control={<Group><Select size="xs" w={180} value={priceId} onChange={setPriceId} placeholder="Инструмент" data={series.map(item=>({value:String(item.id),label:item.ticker||item.name}))}/><Select size="xs" w={105} value={priceDays} onChange={v=>setPriceDays(v||"365")} data={[{value:"30",label:"30 дней"},{value:"90",label:"90 дней"},{value:"180",label:"180 дней"},{value:"365",label:"1 год"},{value:"1095",label:"3 года"}]}/></Group>}>
        {priceData.length?<LineChart h={330} data={priceData} dataKey="date" curveType="natural" series={[{name:"price",label:selected?.ticker||selected?.name||"Цена",color:"teal.6"}]} valueFormatter={formatMoney} gridAxis="y"/>:<Empty text="История цены выбранного инструмента отсутствует"/>}
      </ChartCard>
    </SimpleGrid></>;
}
function ChartCard({kicker,title,control,children}:{kicker:string;title:string;control:React.ReactNode;children:React.ReactNode}){return <Paper withBorder radius="lg" p="xl"><Group justify="space-between" align="flex-start" mb="xl"><div><Text className="section-kicker">{kicker}</Text><Title order={3}>{title}</Title></div>{control}</Group>{children}</Paper>}
function Empty({text}:{text:string}){return <Stack h={330} align="center" justify="center"><Text c="dimmed" size="sm">{text}</Text></Stack>}
function returnBarColor(value:number){if(value>0)return"teal.7";if(value<0)return"red.7";return"gray.6"}
function bucketHistory(history:HistoryPoint[],period:"day"|"week"|"month"){if(period==="day")return history;const buckets=new Map<string,HistoryPoint>();for(const item of history){const day=item.day||item.ts.slice(0,10);const date=new Date(`${day}T00:00:00Z`);if(period==="week")date.setUTCDate(date.getUTCDate()-((date.getUTCDay()+6)%7));const key=period==="month"?day.slice(0,7):date.toISOString().slice(0,10);buckets.set(key,{...item,day:key})}return[...buckets.values()]}
