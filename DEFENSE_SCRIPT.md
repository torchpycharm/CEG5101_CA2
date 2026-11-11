# CA2 答辩讲稿（中英对照）

配合 PPT：https://claude.ai/artifact/GkvntdzT94FGQfwsjzYbLV
每页先是**英文稿（照着说）**，下面是**中文对照**。不含演示约 12 分钟，含演示约 18 分钟；第 25 页是备用页，老师问代码时再翻。

| 部分 | 页码 | 建议时长 |
|---|---|---|
| 开场与概览 | 1–2 | 1 分钟 |
| Task 1 拓扑 + 演示 | 3–5 | 2.5 分钟 |
| 控制器结构 | 6 | 1 分钟 |
| Task 2 检测与封禁 + 演示 | 7–10 | 4 分钟 |
| Task 3 动态代价 | 11–12 | 1.5 分钟 |
| Task 4 改路 + Task 3/4 演示 | 13–16 | 5 分钟 |
| Task 5 性能评估 + 演示 | 17–21 | 2 分钟 |
| 总结与局限 | 22–24 | 1 分钟 |


## 1 · Cover（约 20 秒）

**EN**
Good morning. We are Zhang Fangyu and Yan Zisong. Our project is an anomaly-aware routing and blocking controller. It detects a host that floods the network, blocks it, and moves legitimate traffic onto a better path. I will go through Tasks 1 to 5 in order, and the last slide is a code map in case you would like to look at specific functions.

**中文**
老师好，我们是 ZHANG FANGYU 和 YAN ZISONG。我们做的是一个异常感知的路由与封禁控制器：它能发现在网络里疯狂发包的主机，把它封掉，并让正常流量换到更好的路上。我会按 Task 1 到 Task 5 依次讲，最后一页是代码地图，方便老师看具体的函数。

---

## 2 · What the controller adds（约 40 秒）

**EN**
We started from the two reference programs. resilient_controller.py discovers the topology and computes shortest paths with Dijkstra, but its link costs are fixed. anomaly_detection.py keeps an EMA baseline for each source and installs a drop rule, but after blocking it never reroutes anything.
We combined them and added three things. First, a dynamic cost for every link, based on its load and on whether an attack crosses it. Second, rerouting: whenever costs change, every installed flow is checked for a cheaper path. Third, recovery: when the attack stops, the source is unblocked, the cost is reset and the original path comes back.
Every number in this presentation comes from one complete run, called run4.

**中文**
我们从两份参考代码出发。resilient_controller.py 负责发现拓扑、用 Dijkstra 算最短路，但链路代价是固定的；anomaly_detection.py 为每个源维护 EMA 基线并安装丢包规则，但封完之后不会改路。
我们把两者合在一起，加了三样东西。第一，每条链路的动态代价，取决于它的负载以及有没有攻击经过。第二，改路：代价一变，就检查每条已安装的流有没有更便宜的路。第三，恢复：攻击停了以后解封、代价复原、原路恢复。
这次报告里所有数字都来自同一次完整运行，叫 run4。

> 过渡：First, the topology. / 先看拓扑。

---

## 3 · Task 1 · The mesh topology runs in MiniEdit（约 40 秒）

**EN**
For Task 1, we built ceg_mesh_topo.py in MiniEdit: six switches, six hosts, and eleven links between switches, each at 40 megabits per second with the delays from the topology file. It is saved as miniedit.mn.
After pressing Run, the controller discovered all eleven links through LLDP, as the log shows. ovs-vsctl shows every bridge connected to the controller, and pingall gives zero percent loss.

**中文**
Task 1：我们在 MiniEdit 里搭了 ceg_mesh_topo.py 的拓扑：6 台交换机、6 台主机、11 条交换机之间的链路，每条 40 Mbit/s，时延和拓扑文件一致，保存成 miniedit.mn。
点 Run 之后，日志显示控制器通过 LLDP 发现了全部 11 条链路；ovs-vsctl 显示每个网桥都连上了控制器；pingall 0% 丢包。

---

## 4 · Base costs C0 and the paths that matter（约 50 秒）

**EN**
The assignment defines C0 as the original cost in the provided controller, so we copied its table: s1–s2 is 5, s2–s3 is 10, s1–s4 is 20, s2–s4 is 8, and every other link takes its default of 10.
With these costs, h1 to h6 goes through s1, s2, s6, with a cost of 15. The cheapest alternative is s1, s5, s6, with a cost of 20.
The three attacks load s2–s3, s2–s6 and s5–s6. Please keep in mind that only s2–s6 lies on the h1 to h6 path. This explains why only scenario b reroutes that flow.

**中文**
作业把 C0 定义为所给控制器里的原始代价，所以我们照抄了它的表：s1–s2 是 5，s2–s3 是 10，s1–s4 是 20，s2–s4 是 8，其余链路取默认值 10。
在这组代价下，h1 到 h6 走 s1、s2、s6，代价 15；最便宜的备选是 s1、s5、s6，代价 20。
三次攻击分别加载 s2–s3、s2–s6 和 s5–s6。请记住只有 s2–s6 在 h1 到 h6 的路上，这就解释了为什么只有场景 b 会让这条流换路。

> 过渡：Now, how the controller is organised. / 接下来看控制器的结构。

---

## 5 · Demo · Task 1 commands（现场演示，约 1 分钟）

**EN**
Let me show this live. In terminal one I start the controller, in terminal two I open MiniEdit, load miniedit.mn and press Run. You can see the link count reach eleven, every switch is connected, and h1 can ping h6.

**中文**
现场演示一下。终端 1 启动控制器，终端 2 打开 MiniEdit，载入 miniedit.mn 并点 Run。可以看到链路数涨到 11，所有交换机都已连接，h1 能 ping 通 h6。演示完：MiniEdit 点 Stop，终端 1 按 Ctrl+C，执行 sudo mn -c。

---

## 6 · Controller design: one 2-second loop（约 1 分钟）

**EN**
The controller has two parts. On the right are event handlers: when a packet reaches the controller, it learns where the host is and sets up a path; when a port goes down, it removes the link and reroutes.
The core is the loop on the left, which runs every two seconds. It always does the same steps in the same order: measure the rate of every source and every link, detect and block, release sources that have gone quiet, update link costs, reroute installed flows, and write the logs.
Because these steps run in one pass, detection, blocking, the cost increase and the reroute all happen in the same poll. In run4 they all happened 1.2 seconds after each attack started.
At the bottom right you can see the rule priorities: the drop rule at 5000 overrides everything, then our ICMP counters at 11, forwarding at 10, and the table-miss rule at 0.

**中文**
控制器分两部分。右边是事件处理：有包送到控制器时，学习主机位置并建立路径；端口断开时，删掉链路并改路。
核心是左边每 2 秒运行一次的循环，每次按同样的顺序做同样的事：测每个源和每条链路的速率，检测和封禁，解封已经安静的源，更新链路代价，给已安装的流改路，写日志。
因为这些步骤在同一轮里完成，所以发现攻击、封禁、代价上升和改路都发生在同一次轮询里。run4 中每次都是攻击开始后 1.2 秒。
右下角是规则优先级：丢包规则 5000 最高，然后是我们的 ICMP 计数规则 11、转发规则 10、table-miss 规则 0。

> 过渡：Let me start with Task 2, detection and blocking. / 先讲 Task 2，检测与封禁。

---

## 7 · Task 2 · Detecting an abnormal source（约 1 分钟）

**EN**
The detection rule is the same as in the reference code. The baseline is an exponential moving average with alpha 0.3, and a source is anomalous when its rate exceeds three times its baseline.
We changed three things. First, the rate is measured only at the source’s own access switch, so each packet is counted once; the reference code counts it again on every switch it passes. Second, we compare first and then update, and an anomalous sample never enters the baseline. Otherwise a long flood would keep raising its own baseline until it no longer looks abnormal. Third, we added a floor of 1000 packets per second and a warm-up of three samples. Background pings give baselines of only one or two packets per second, so three times that would trigger on a simple pingall.
Once a source is flagged, we install a drop rule on all six switches, priority 5000, matching its source IP. We then watch that rule’s counter, and after three quiet polls the source is released.

**中文**
检测规则和参考代码一样：基线是 α=0.3 的指数移动平均，速率超过基线 3 倍就判定为异常。
我们改了三处。第一，速率只在源主机自己的接入交换机上测量，每个包只算一次；参考代码会在经过的每台交换机上重复计数。第二，先比较再更新，异常样本永远不进入基线，否则持续的洪泛会不断抬高自己的基线，直到看起来不再异常。第三，加了每秒 1000 包的下限和 3 个样本的预热，因为背景 ping 的基线只有每秒 1 到 2 个包，3 倍的门槛一次 pingall 就会触发。
一旦判定异常，就在全部 6 台交换机上安装优先级 5000、匹配该源 IP 的丢包规则。之后观察这条规则的计数器，连续 3 轮安静就解封。

---

## 8 · Task 2 · Not blocking the victim（约 1 分钟）

**EN**
This was the hardest problem we met. During an ICMP flood the victim answers every Echo Request, so it sends Echo Replies at the same rate as the attack. A detector that counts every packet by source address therefore flags the victim too. In scenarios b and c the victim is h6, which is the destination of the flow we are protecting, so blocking it would cut exactly the traffic we want to keep.
Our first version did this. Our second version subtracted the requests a host received from the replies it sent within the same poll, but statistics from different switches arrive at different times, so requests and replies often fall into different polls.
The final version separates them in the data plane. On the source’s access switch we add two priority-11 rules that match Echo Request and Echo Reply and forward exactly like the normal rule, so forwarding is unchanged but each type has its own counter. The source rate simply leaves out Echo Replies.
The result: in scenario a, h3 sent 41,311 replies per second, yet the controller counted only 1.0 packet per second for h3, which is its background ping.

**中文**
这是我们遇到的最难的问题。ICMP 洪泛时，受害者会回复每一个 Echo Request，所以它发出 Echo Reply 的速度和攻击一样快。按源地址统计所有包的检测器因此会把受害者也判为异常。在场景 b 和 c 中受害者是 h6，也就是我们要保护的流的目的地，封了它就等于切断了我们要保留的流量。
我们的第一版就是这样。第二版在同一轮里用主机收到的请求去抵扣它发出的回复，但不同交换机的统计是在不同时间到达的，请求和回复常常落在不同轮次里。
最终版在数据平面把两者分开：在源主机的接入交换机上加两条优先级 11 的规则，分别匹配 Echo Request 和 Echo Reply，转发方式和普通规则完全一样，所以转发不变，但每种类型有了自己的计数器。源速率直接不算 Echo Reply。
结果：场景 a 中 h3 每秒回复 41,311 个包，控制器给 h3 算出的速率只有每秒 1.0 个，也就是它的背景 ping。

---

## 9 · Task 2 · Manual run of scenario a（约 40 秒）

**EN**
This is a manual run of scenario a. On the left, after pingall, h2 pings h3 once a second to build its baseline, and then floods h3 with hping3 for 20 seconds.
On the right, the controller reports the anomaly: 40,255 packets per second against a baseline of 2. It blocks only 10.0.0.2. The victim h3 is not blocked. Then it reroutes the flows that crossed s2–s3.
To verify the block, we queried the switches twice. The drop rule on s2 went from 21,079 to 153,649 packets in 1.85 seconds, so the flood is dropped at the ingress. The h2-to-h3 forwarding rule on s3 stayed at 112,172, so no flood packet reaches h3 any more. After the flood stops, h2 is released automatically.

**中文**
这是场景 a 的手动运行。左边：pingall 之后，h2 每秒 ping 一次 h3 建立基线，然后用 hping3 对 h3 洪泛 20 秒。
右边：控制器报告异常，每秒 40,255 个包，基线是 2；只封了 10.0.0.2，受害者 h3 没有被封；接着把经过 s2–s3 的流改了路。
为了验证封禁生效，我们查询了两次交换机：s2 上的丢包规则在 1.85 秒内从 21,079 涨到 153,649 个包，说明洪泛在入口就被丢掉了；s3 上 h2 到 h3 的转发规则一直是 112,172，说明不再有攻击包到达 h3。洪泛停止后，h2 被自动解封。

> 过渡：Next, Task 3, the dynamic cost. / 接下来是 Task 3，动态代价。

---

## 10 · Demo · Task 2 commands（现场演示，约 1.5 分钟）

**EN**
Now the same attack live. After pingall, h2 pings h3 once a second to build its baseline. Then h2 floods h3 for twenty seconds. Within about two seconds the controller prints ANOMALY and BLOCK for 10.0.0.2 only. On s2 the drop rule counter keeps growing, while the h2-to-h3 rule on s3 stays the same. About seven seconds after the flood, h2 is released.

**中文**
现场再跑一次同样的攻击。pingall 之后，h2 每秒 ping 一次 h3 建立基线；然后 h2 对 h3 洪泛 20 秒。大约 2 秒内控制器打印 ANOMALY 和 BLOCK，只针对 10.0.0.2。s2 上丢包规则的计数一直在涨，s3 上 h2 到 h3 的规则计数不变。洪泛结束约 7 秒后 h2 被解封。

---

## 11 · Task 3 · Dynamic link cost（约 50 秒）

**EN**
The cost formula is the one in Reference C: C equals C0, plus alpha times the load, plus beta times the anomaly flag.
The load R is measured from the switch port byte counters every two seconds. We take the busier of the two directions and smooth it, then divide by Rmax, which is the link bandwidth of 40 megabits per second.
The flag A is 1 on every link of the blocked source’s flood path, and it goes back to 0 when the source is released.
We chose alpha equal to 10, so a fully loaded link costs about twice a default link; load alone moves traffic only under heavy congestion. We chose beta equal to 20, which is larger than any gap between the main path and its alternative, for example 20 minus 15 for h1 to h6. So a flagged link is always avoided when there is another path. But beta is finite, so if the flagged link is the only path, it is still used and connectivity is kept.

**中文**
代价公式就是 Reference C 的那条：C 等于 C0，加 α 乘以负载，再加 β 乘以异常标记。
负载 R 每 2 秒从交换机端口的字节计数算出，取两个方向中较忙的那个并做平滑，再除以 Rmax，也就是链路带宽 40 Mbit/s。
标记 A 在被封源的洪泛路径的每条链路上为 1，源被解封后变回 0。
我们取 α=10，所以满载链路的代价大约是默认链路的两倍；只有在严重拥塞时，负载本身才会让流量换路。取 β=20，它比主路和备选路之间的任何代价差都大，比如 h1 到 h6 是 20 减 15，所以只要有别的路，被标记的链路一定被避开。但 β 是有限的，如果被标记的链路是唯一的路，仍然会被使用，连通性得以保持。

---

## 12 · Task 3 · The cost of each flooded link（约 40 秒）

**EN**
In all three scenarios the flooded link behaves the same way. At the first poll after the attack starts, the load term and the anomaly term rise together, and the cost reaches about 3.1 to 3.2 times its base value.
In the same poll the attacker is blocked and the flood is dropped at the ingress, so the load on the link falls to zero. The anomaly term stays, so the cost holds at exactly 3.0 times, which is 10 plus 20, over 10.
Seven point two seconds after the flood stops, the source is released, A goes back to 0 and the cost returns to C0.
Notice that s2–s6 is already at 1.13 before scenario b, because the 5-megabit h1-to-h6 flow uses it. The load term follows real traffic.

**中文**
三个场景里被攻击的链路表现一样：攻击开始后的第一轮，负载项和异常项同时上升，代价达到基础值的约 3.1 到 3.2 倍。
同一轮里攻击者被封，洪泛在入口被丢掉，所以这条链路上的负载降为零；异常项还在，所以代价稳定在 3.0 倍，也就是 10 加 20 再除以 10。
洪泛停止 7.2 秒后，源被解封，A 变回 0，代价回到 C0。
注意场景 b 之前 s2–s6 就已经是 1.13 倍，因为 5 Mbit/s 的 h1 到 h6 流在用这条链路。负载项跟随的是真实流量。

> 过渡：Now, Task 4, rerouting. / 接下来是 Task 4，改路。

---

## 13 · Task 4 · How a flow is rerouted（约 50 秒）

**EN**
Rerouting works in three steps. First, Dijkstra runs on the current costs. It is the same algorithm as in the reference code; only the weights now change over time.
Second, after every cost update we check every installed flow, and we move it only if the new path is cheaper by more than 2. This margin stops a flow from switching back and forth, for example because its own load makes the new path slightly more expensive.
Third, we make the new path before we break the old one. Rules are written from the destination switch back to the source, so a packet never reaches a switch that has no rule yet. Rules that already exist are modified in place, because adding them again would reset the counters we use to measure rates. Rules on switches that are no longer used are deleted last.

**中文**
改路分三步。第一，在当前代价上运行 Dijkstra，算法和参考代码一样，只是权重现在会随时间变化。
第二，每次代价更新后检查每条已安装的流，只有新路比当前路便宜超过 2 才换。这个余量防止流来回切换，比如流自己的负载让新路稍微变贵。
第三，先建新路再拆旧路。规则从目的交换机往源端倒着写，所以包永远不会走到一台还没有规则的交换机；已经存在的规则原地修改，因为重新添加会清零我们用来测速的计数器；不再使用的交换机上的规则最后删除。

---

## 14 · Task 4 · h1→h6 before any anomaly（约 40 秒）

**EN**
Before any attack, we start a constant 5-megabit UDP flow from h1 to h6, plus a ping every 0.1 seconds. Its path is s1, s2, s6. The path cost is 15 from C0 alone, or 17.59 including its own load. Throughput is 5.00 megabits per second, with zero UDP loss and zero ping loss, and the round-trip time is 98.5 milliseconds, which matches the link delays.
The table shows the cost of each candidate path at the first poll of each flood, with the selected path in bold. In scenarios a and c, s1–s2–s6 stays the cheapest. Only in scenario b does it rise to 38.30, so the flow moves to s1–s5–s6 at 20.

**中文**
攻击之前，我们让 h1 向 h6 持续发 5 Mbit/s 的 UDP，同时每 0.1 秒 ping 一次。路径是 s1、s2、s6，只看 C0 的代价是 15，加上它自己的负载是 17.59；吞吐 5.00 Mbit/s，UDP 和 ping 都不丢包；往返时间 98.5 毫秒，和链路时延相符。
表里是每次洪泛第一轮时各候选路径的代价，加粗的是选中的路径。场景 a 和 c 中 s1–s2–s6 一直最便宜；只有场景 b 中它涨到 38.30，所以流换到代价 20 的 s1–s5–s6。

---

## 15 · Task 4 · Three floods, one reroute（约 40 秒）

**EN**
This table answers requirements a to f for each scenario.
In every case the flooded link rises from about 10 to above 30. The attacker is detected about 1.2 seconds after the flood starts, and only the attacker is blocked.
Only scenario b reroutes h1 to h6, from s1–s2–s6 to s1–s5–s6. In a and c the flooded link is not on its path, so it correctly stays where it is. Other flows that did cross the flooded link were moved.
Throughput stays at 5 megabits per second, and not a single ping is lost, so the flow is never disconnected. The only loss is 34 UDP datagrams in scenario b, all in the second before the block took effect.
Seven point two seconds after each flood, the cost recovers, and in b the original path comes back.

**中文**
这张表逐项回答每个场景的要求 a 到 f。
每个场景中，被洪泛的链路代价都从 10 左右升到 30 以上；洪泛开始后约 1.2 秒检测到攻击者，并且只封攻击者。
只有场景 b 让 h1 到 h6 换路，从 s1–s2–s6 换到 s1–s5–s6。a 和 c 中被洪泛的链路不在它的路上，所以它正确地保持不动；经过被洪泛链路的其他流确实被换走了。
吞吐一直是 5 Mbit/s，一个 ping 都没丢，流从未中断。唯一的损失是场景 b 中的 34 个 UDP 数据报，全部发生在封禁生效前的那一秒。
每次洪泛结束 7.2 秒后，代价恢复，场景 b 中原路也恢复了。

> 过渡：Task 5 shows the same results over time. / Task 5 用时间曲线展示同样的结果。

---

## 16 · Demo · Tasks 3 and 4 in one run（现场演示，约 3 分钟）

**EN**
Tasks 3 and 4 run with one command. The script starts the controller and the topology, runs a twenty-second baseline, and then the three floods. Two windows open: the controller output on the left and the live view on the right. In a and c, the flooded link turns red and its cost reaches about three times, but h1 to h6 stays on s1–s2–s6. In b, you will see the reroute to s1–s5–s6 and the RTT rise to about 137 milliseconds, while throughput stays at 5 megabits per second. After each flood, everything recovers in about seven seconds.

**中文**
Task 3 和 4 用一条命令跑完。脚本会启动控制器和拓扑，先跑 20 秒基线，再依次做三次洪泛。会弹出两个窗口：左边是控制器输出，右边是实时面板。a 和 c 中，被洪泛的链路变红、代价约 3 倍，但 h1 到 h6 保持在 s1–s2–s6；b 中可以看到它改到 s1–s5–s6，RTT 升到约 137 毫秒，吞吐仍是 5 Mbit/s。每次洪泛后约 7 秒一切恢复。现场跑不起来时，用最后一行命令回放 run4。

---

## 17 · Task 5 · Normalised link cost vs time（约 25 秒）

**EN**
This is the normalised cost over time. The grey bands are the three floods. Each flooded link jumps to about three times its base cost and returns to one after release. The orange line, s1–s5, rises to 1.13 only in scenario b, because h1 to h6 is moved onto it.

**中文**
这是归一化代价随时间的变化，灰色区域是三次洪泛。每条被洪泛的链路都跳到基础代价的约 3 倍，解封后回到 1。橙色的 s1–s5 只在场景 b 中升到 1.13，因为 h1 到 h6 被换到了它上面。

---

## 18 · Task 5 · Packet loss of h1→h6 vs time（约 25 秒）

**EN**
Packet loss stays at zero. None of the 2,102 pings was lost. Of 109,255 UDP datagrams, 34 were lost, which is 0.031 percent, all at the start of scenario b before the block. The spike appears slightly before the grey band because iperf3’s one-second reports lag the experiment clock by about half a second.

**中文**
丢包率一直是零。2,102 个 ping 一个没丢；109,255 个 UDP 数据报丢了 34 个，占 0.031%，全部在场景 b 开始、封禁之前。尖峰显示在灰色区域稍前一点，是因为 iperf3 每秒的报告比实验时钟慢约半秒。

---

## 19 · Task 5 · Throughput of h1→h6 vs time（约 25 秒）

**EN**
Throughput stays at 5 megabits per second in every phase. The dip to 4.67 is the same loss at the start of b. The small peak of 5.1 appears when the path switches back: packets on the shorter new path overtake those still on the longer old path. That is reordering, not loss.

**中文**
吞吐在每个阶段都保持 5 Mbit/s。降到 4.67 的那一下就是场景 b 开始时的同一次丢包。5.1 的小尖出现在换回原路时：短的新路上的包追上了还在长的旧路上的包，这是乱序，不是丢包。

---

## 20 · Task 5 · RTT shows the path change（约 25 秒）

**EN**
We added one more plot, the round-trip time, because it shows the path change directly. It is 98.5 milliseconds on s1–s2–s6 and 136.6 milliseconds on s1–s5–s6. The detour is longer because it uses the two slowest links in the network, 18 and 20 milliseconds, which have the default cost of 10 in the reference table.

**中文**
我们多画了一张往返时间图，因为它直接显示了路径变化：s1–s2–s6 上是 98.5 毫秒，s1–s5–s6 上是 136.6 毫秒。绕行更长，是因为它用了网络中最慢的两条链路，18 和 20 毫秒，而参考代价表给它们的都是默认值 10。

> 过渡：What did we learn from this? / 从结果里我们得到了什么？

---

## 21 · Demo · Task 5 commands（现场演示，约 30 秒）

**EN**
From the run we just did, summarize_run produces the numbers for requirements a to f, and plot_results draws the figures. I open the folder in Explorer and show the overview plot first.

**中文**
用刚才那次运行的结果，summarize_run 生成 a 到 f 的数字，plot_results 画图。在资源管理器里打开文件夹，先展示 overview.png。如果现场没跑，就打开 results/run4/plots。

---

## 22 · Key result（约 30 秒）

**EN**
The most important lesson is this: rerouting protects the shared transit links, but only blocking protects the victim’s own access link.
In scenario b the attack and the legitimate flow share s2–s6, which we can avoid, and also the link from s6 to h6, which we cannot, because h6 is the destination of both. We measured 760 packets dropped in the queue towards h6 during that second, with zero receive-buffer errors on h6. So the 34 lost datagrams were lost in the network before the block. Both mechanisms are needed.

**中文**
最重要的一点是：改路保护的是共享的中转链路，只有封禁才能保护受害者自己的接入链路。
在场景 b 中，攻击和合法流共用 s2–s6，这可以避开；还共用 s6 到 h6 的链路，这避不开，因为 h6 是两者共同的目的地。我们测到那一秒里通往 h6 的队列丢了 760 个包，而 h6 的接收缓冲错误为零。所以那 34 个数据报是在封禁之前、在网络里丢的。两种机制缺一不可。

---

## 23 · Results in five numbers（约 30 秒）

**EN**
To summarise in five numbers: detection and blocking in 1.2 seconds; only the attacker blocked in all three floods; zero of 2,102 pings lost; 5 megabits per second kept in every phase; and full recovery 7.2 seconds after each flood. Rerouting is selective: only the flow whose path is hit is moved.

**中文**
用五个数字总结：1.2 秒内检测并封禁；三次洪泛都只封了攻击者；2,102 个 ping 零丢失；每个阶段都保持 5 Mbit/s；每次洪泛后 7.2 秒完全恢复。改路是有选择的：只有路径被攻击的流才会被换走。

---

## 24 · Limitations and how we would improve them（约 30 秒）

**EN**
Finally, some limitations. Detection waits for the next poll, so the flood reaches the victim for about a second; OpenFlow meters could rate-limit at the access port instead. The 1000-packet floor misses low-rate or many-source attacks. Blocking by IP can be evaded by spoofing and also cuts the attacker’s normal traffic. A flood made only of Echo Replies is not counted against its sender. And C0 ignores delay, which is why the detour adds 38 milliseconds; a delay-based C0 is already implemented as an option.
Thank you. We are happy to take questions.

**中文**
最后是一些局限。检测要等下一次轮询，所以洪泛会到达受害者约一秒，可以改用 OpenFlow meter 在接入端口限速。1000 包的下限检测不到低速攻击或多源攻击。按 IP 封禁会被伪造地址绕过，也会切断攻击者的正常流量。只由 Echo Reply 组成的洪泛不会算到发送者头上。还有 C0 不考虑时延，所以绕行多了 38 毫秒；基于时延的 C0 已经作为选项实现了。
谢谢老师，欢迎提问。

---

## 25 · Backup · Code map（提问时使用）

**EN**
If you would like to see the code, this table lists each core function and its lines. I suggest following the order of the loop: _measure_sources, which leaves out Echo Replies; _check_anomalies, with the threshold and compare-then-update; _block_ip and _check_recovery; _update_costs, with the formula; and finally _reroute_flows and _install_path, which move a flow without a gap.

**中文**
如果老师想看代码，这张表列出了每个核心函数和行号。建议按循环的顺序讲：_measure_sources，不计 Echo Reply；_check_anomalies，门槛和先比较后更新；_block_ip 和 _check_recovery；_update_costs，代价公式；最后是 _reroute_flows 和 _install_path，无中断地换路。

逐行讲解见 [DEFENSE_CODE_WALKTHROUGH.md](DEFENSE_CODE_WALKTHROUGH.md)。

---

## 常见追问的英文短答

| 问题 | 英文回答 |
|---|---|
| How does the attack work? | `hping3 --icmp --flood` sends ICMP Echo Requests from h2 to h3 as fast as possible without waiting for replies; `timeout 20` stops it after 20 seconds. |
| Why not block the victim? | The victim only replies. We count Echo Requests and Echo Replies separately and leave the replies out of the source rate. |
| Why is h1→h6 not rerouted in a and c? | The flooded link is not on its path, so its cost does not change and s1–s2–s6 is still the cheapest. |
| What if there is no alternative path? | β is finite, so the flagged link is still used and the flow stays connected. |
| Why rules from destination to source? | So the path ahead is ready before the source switch changes direction; no packet meets a switch without a rule. |
| Why MODIFY instead of ADD? | Adding an identical rule resets its counters, and we need the counters to measure rates. |
| How do you know the attack stopped? | The drop rule keeps counting the attacker’s packets; three quiet polls in a row mean it has stopped. |
| How long does detection take? | At most about 2.5 seconds: one 2-second poll plus 0.5 seconds for the replies. In run4 it was 1.2 seconds. |
