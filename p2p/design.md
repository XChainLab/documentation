#### 基本架构
   从职责划分上来讲， p2p模块可分为俩块：_发现服务_、_消息传输服务_。发现服务主要用来获取更多节点信息，使得消息传输服务与其他节点建立链接时有更多的选择， 节点信息包括IP、端口、协议、节点ID等，链接到更多的节点意味着在以下方面有更大概率：更新本地状态、同等算力下更多的节点收到本地挖出的block。消息传输服务，顾名思义，就是用来传输消息的，比如共识消息、状态同步消息、心跳包、tx/block广播消息等。 消息传输服务从业务深度上可划分为：
   + 链接资源申请管理
   + 协议/代码版本检测
   + 密钥生成与同步
   + 调度其他模块消息
   + 链接资源释放管理

##### 发现服务
主流公链的发现服务一般分为三个部分： 
  1. 节点信息的持久化与查询
  2. 引擎部分：维护链接池、调度发现服务
  3. 节点发现， 主要使用pex、dht算法，概括的来讲:
+ pex是在已建立连接的俩个节点之间交换已知节点信息
+ dht解决了p2p的中心化tracker 的问题，该算法包括三个步骤： 
    - A节点广播一个（hash， entry）的键值对， 一般为(节点ID, NetworkAddr)
    - B将(hash, entry)加入本地table
    - 使用table 提供 lookup service 

##### 消息传输服务
p2p的消息传输服务应该不仅作为server通过监听端口处理链接请求， 还需作为client发起链接， 俩个方向的链接都应通过令牌的方式控制连接数。仅作为server处理链接会导致一系列的攻击比如女巫攻击；仅作为client发起链接会失去大量链接的机会，因为其他节点发起与本节点的链接失败后会抛弃本节点信息。此过程有俩个细节需要说明：
+ 节点之间保持一个链接即可，不要漏过处于dialing状态的节点
+ 需要标识是链接的发起方还是监听方，原因是:
  - 后续的心跳等模块可能需要区分， 发起方作为client需要维持心跳
  - 释放链接是需要依据标识释放归还不同的令牌

为了保证消息的完整性， 以太仿使用如下的消息报文格式来拆解包
```golang
| length| msgHash | msg |
```

在具体的业务逻辑开始前进行本代码版本检测可以实现控制代码升级、分叉，进行协议检测可以避免大量无效链接。目前以太仿的节点分为俩种full node、light node, 即将到来的sharding版本又增加了更多的节点角色类型， light node仅同步header信息以及向full node请求merkel proof， 而full node是否支持为light node提供服务就需要在这一步确认。 

区块链建立在非对称加密算法ECC上，非对称加密算法做加解密效率很低，此外ECC是无法用来加解密信息只用用来加密、验证， 所以提供消息隐私性功能需要借助对称加密算法比如AES算法。一般使用STS实现AES的密钥同步， 算法如下

```golang
concat := func(a, b uint)uint{ 
     v, _ := strconv.Atoi(fmt.Spintf("%d%d", a, b))
     return uint(v)
} 
mod := func(x, y uint)uint{
    return x % y
}
pow := func(x, y)uint{
  return uint(math.Pow(x, y))
}
算法：
A, B : set p = 23, g = 5 
A    : generate a = 6,  set va=mod(concat(g, a), p)=8 , sendTo(B,  8) // 56 % 23 == 8 
B    : generate b = 15,  set vb=mod(concat(g, b), p)=19 , sendTo(A,  19) // 515 % 23 == 19 
A    : set secret=mod(pow(vb, a), p)=2 // 47045881 % 23=19
B    : set secret=mod(pow(va, b), p)=2 // 35184372088832% 23 = 2

密钥安全性保证证明如下:
  +----------节点A-------------+-------节点B----------+---恶意节点 -----------+
  +                           +                      +                      + 
  已知信息  a,p,g,concat,mod   +  b, p,g,concat,mod   +  p,g,concat,mod      +   
  +                           +                      +                      + 
  已知信息  vb, a, p, pow, mod +  va, a, p, pow, mod  +    p, pow, mod       + 
  +                           +                      +                      +
  已知信息    secret           +   secret             +         -            +
  +-------------------------------------------------------------------------+
```

主流的公链包括若干个模块比如：共识、交易池、账本、P2P等。 共识模块需要通过P2P 广播投票信息、收集投票出块；交易池将验证tx通过p2p 广播给周围节点， 通过p2p收集tx验证后加入本地交易池；账本通过p2p同步账本信息，比如我们可以在心跳包中加入账本高度， 账本模块对比本地高度请求block。
以太仿的交易池模块业务流程如下：
1. 接收tx （来源包括rpc调用、p2p转发等）
2. tx验证（包括nonce， value、gas、signature）后加入本地交易池， 并依据tx中的nonce本地删除老旧tx
3. 以及gasprice对交易池里的tx排序 
4. 为出块模块（挖矿、共识）提供tx list
5. 调用p2p广播验证过的tx 
6. 监听eventhub的“挖矿”主题，删除本地交易池中已经被出块模块打包进入block的tx
7. 监听eventhub的”新块“主题，删除本地交易池中已经其他节点打包进入block的tx
我们可以清晰的看到p2p与交易池的交互发生：1、5。交易池与p2p调用实现大致如下
```golang
type Message struct{
   topic string    // 消息主题， 此处是 txpool
   payload []byte  // 消息体， 解析方式需由各模块自定义 推荐google/proto.Marshal/Unmarshal
}
type Context interface{
	Send(uint32, []byte)  // 模块调用p2p向远程节点发送消息
	ID() string           //  节点标识符
   ...
}

type PeerHandler interface {
	NewPeer(Context)TopicHandler
   ...
}

type TopicHandler interface {
	Handle(uint32, []byte) error // 远程节点向本节点发消息
   ...
}

func readLoop(conn Conn){
   for{
      data := conn.Read() // 消息完整性检测、数据加解密在conn层完成
      go disptath(data)
      ......
   }
}

var mTopicHandler map[string]TopicHandler

func dispatch(data []byte){
   topic, code, payload := decode(data) // 
   h, exists := mTopicHandler[topic]
   if exists{
      h.Handle(code, payload)
   }
   ......
}

type TxPoolServer server{
   txHandlers map[string]txHandler
}

func (self *TxPoolServer)NewPeer(ctx context)TxPoolHandler{
   h := txHandler{...}
   self.txHandlers[ctx.ID()] = h
   ......
   return h
}

func (self TxPoolServer)broadcastTx(tx Transaction， except func(string)bool){ // 广播交易
   payload = encode(tx)
   for id, h := range self.txHandlers{
      if except!=nil && except(id){  // 哪些节点不能发
         continue
      } 
      h.Send(1, payload)
   }
}

func (self txHandler)Handle(code uint, msg []byte)error{
   switch code{
   case 1: // new tx
      ......
   }
   return nil
} 

```

链接client端应该负责发送心跳包维持链接， server端释放不活跃、异常的client; 释放链接的同时应该同步通知与该节点交互的各个子模块。



