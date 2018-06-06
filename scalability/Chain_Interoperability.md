跨链交易难点在于保证交易的原子性，比如ETH兑换BTC其实至少发生俩笔交易，分别发生在ETH和BTC上, 必须俩笔交易要么同时成功， 要么一笔失败的时候俩笔交易必须同时失效， 具体到实现就需要 1 如何获取另一条链上的消息 , 2 怎么保证消息可靠, 3 如何应对在另一条链上期待的转账
+ _针对1、2：1>通过可信的中介结构收听对方链上的消息， 2>通过在本链上维护一个对方链的轻节点作为可信的消息源处理其他合约验证请求_
+ _针对3：  通过deposit一笔锁定资金到某个合约，1> 由中介决定是否放行, 2> 由合约判断对方提交的证据判断是否放行_
	
针对以上的三个问题决绝方案不同，市面上流行的跨链解决法案有：中介、中继, hash locking； 中继的典型代表有BTC-repy、cosmos-hub, 中介的典型代表有撮合交易, hash locking 典型的有雷电网络， 撮合交易系统不再赘述。   
1. BTC Replay的实现分为三个部分：  (假设 Alice 用eth 购买 Bob手里的btc)
+ _将BTC的header搬到eth的合约上， 通过该合约可以视为是维持了一个btc header 的轻节点， 它可以使用SPV验证某个tx 是否发生了，为了鼓励大家提供btc的header， 可以允许给提供header信息的节点设置服务费_
+ _Alice deposit eth到某个负责转账的contract， 该contrct 的作用允许任何人提供验证btc转账发生该节点负责调用eth 上的btc 轻节点合约 验证tx的有效性然后 然后通过解析btc上的tx来判断某个addr 是否收到了足够的BTC, 验证通过给Bob的eth 地址转账_
+ _Bob 发现Alice deposit足够的eth到转账合约后， 给Alice在BTC上的地址上转账_

**_同样我们可以将这一模式搬到任何支持智能合约的公链X上_**

2. cosmos 其实由tendermint驱动的一个公链架构的方案， 它不是一条具体的链， tendermint 是一个pos  + pbft 驱动的可插拔公链的基础架构，tx 的验证、block 的apply 通过调用RPC执行， p2p作为 tendermint 的入口， 其他部分比如 consensus、mempool、blockchain等通过向p2p注册reactor接口的方式驱动， 各个模块间通过event hub的相互驱动，
tendermint 进一步修改了经典pbft的算法， proposer 通过节点在pos中的 despoit 的数量设置可发起提案的权重， 通过权重计算下一轮的proposer写入本次提案中， 下一轮发起是验证节点先判断自己是否有资格发起提案， 将经典的三步 完成commit， 演化成俩步完成。 在RPC调用block apply 的时候会更新快上的验证节点集合。
cosmos 做跨链的转账的解决方案如下( 假设 Alice 用eth 购买 Bob手里的btc)
+ _创建一条称之为Hub(实现cosmos方案的公链)的公链， 通过 hub字面义可以看出这一条消息负责消息分发的公链_
+ _在ETH创建一条侧链（我们称之为 Z1）， 在ETH上部署一个合约负责押金接受、放行等，这条侧链可以用tendermint驱动的也可以方案实现的，该侧链的作用1> 跟踪该contract上发生的交易， 对交易签名后发给HUB， 2>负责对发出的消息验证, 3> 接受可信的消息后调用contract的给Bob转账_ 
+ _在receiver 所在的公链同样的创建一条类似于z1的公链Z2，作用与2相同_


3. [雷电网络](https://github.com/XChainLab/documentation/tree/master/scalability/raiden)

 




