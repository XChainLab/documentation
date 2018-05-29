**_先给出大白话的总结_** ： 试想ABCD四个小伙伴做游戏，游戏中有一步是资金转账， 最一开始他们都知道其他人的可用资金， 为了方便也出于信任的原因， 他们之间的转账都通过打白条的方式， 白条也是可用的资金， 比如A给B打了个10元的白条， 那么A就知道B比刚才多了10元， B若要给A转账的话， A处认可的B的可用资金会比开始时多了10元，但是这就造成了几个潜在的问题， 1：随着时间的推移小伙伴之间无法准确的知道对方的剩余可用资金， 因为资金流向是多方向的， 2：这些白条怎么兑现，无论对方对方承认与否的情况下怎么兑现， 3：有人造假怎么办
+ 针对1： 让资金单向流动， 我们规定所有的小伙伴之间俩俩配对， （A,B）（B,C）(C,D)就是一种可能的组合， 转账只能在配对的组合内或者通过对内的小伙伴转给外部小伙伴， 这样就保证了， 小伙伴的剩余可用资金对于对内的伙伴永远是可查的， 但是这也带来了一个问题跨对转账怎么完成例如A给D转账， 解决方案是我们规定（A，B）是一条边， 那么A需要找到一条A到D的通路， 转账就发生在这条通路上，所以此时A知道 A->B ->C ->D 是一条通路， 另外我们也规定这样的路上的转账的资金必须被锁定（意思是组内收到白条的一方的可用资金不会增加，打白条的一方的可用资金会减少）， 那么A就给B打个锁定资金的白条， 白条是有附带信息“知道了secret才能解锁资金, 计算方法是hash(secret, lockhash')==locksroot， 其中lockhash'是上一笔该小组内的处于锁定状态白条的的lockhash ”才能生效， B也照此给D打个白条， C同样如此给D打白条， D收到白条后告诉A， 他收到白条了， 那么此时A就把这笔解锁这笔资金的secret告诉D， 但是此时资金还是处于锁定状态，D的可用资金没有增加（是否增加取决组内的C是否承认）， 如果强制解锁资金的话友谊的小船会翻的， 那么他会立刻告诉C他收到了secret， C就会重新打个条子并添加额外的信息“为友谊的小窗不翻，这个白条是用来抵消刚才的锁定的那笔资金， 同时也表示那笔处于锁定状态的白条无效了”， 如此重复直到A处 ， 细心的同学可能发现B出现在俩个组内就意味B的可用资金double了， 事情肯定不这么简单， 我们规定这种情况下B的资金必须拆分为俩分。
+ 针对2： 我们强制规定1： 必须和其他小伙伴组队， 2：组队的同时必须交一笔押金， 所以 可用资金就 == 押金，3:增加一个裁判的角色，押金交到裁判这里， 裁判负责仲裁
+ 针对3： 每个白条必须有自己签名， 裁判只认签名然后按规矩办事

普通白条的定义 ：

```python
{ 
    transfer_amount, //（总计转出去了多少钱， 注意不是现在要转多少）, 
    nonce,//（第几次转账），
    locksroot,//(处于锁定状态的资金有哪些)， 
    signature, 
    hash(transfer_amount, nonce, locksroot),
}
```

这么定义的好处
..* transfer_amount 1：接收方只需要保存最后一个白条即可， 2： 防止重放攻击，裁判只给你判决一次（所以你只会拿着最后一张白条去提现）
..* locked_transfer：1: 防止通道上锁定资金在收到普通的白条后强制解锁资金， 因为解锁锁定白条的的白条会删了锁定的那个条子

锁定资金的白条 

```python
{
    amount， //本次要锁定的资金 
    nonce,
    hash(amount, nonce, locksroot'), 
    locksroot, // locksroot = hash(locksroot‘, nonce, secret), locksroot‘ 表示上一笔锁定的锁定资金白条中的,找裁判兑现这个白条必须要知道secret才可以
    signature,
}
```

具体的操作
1： 怎么提现？
... 组内成员每人一次提交普通白条的机会， 提交锁定白条的次数不受限制， 但是你得按照 merkel proof姿势去解锁每一笔锁定的白条
2： 怎么找到小伙伴？
... 可以随机加入， 可以自由组合， 但是一旦组成立了， 游戏内的其他小伙伴会发来贺电， 因为他们可能会借用你们的通道
3： 有什么瓶颈， 怎么解决?
... 跨组转账的话， 你得借用别人的资金池， 所以找到一条合适的通道就需要俩个条件  1：有一条可到达的路， 2： 路上的小伙伴之间的认可可用资金小于你们转的资金数目， 这会造成热点故障， 若进一步造成恶化的话， 就会脑裂，原因是1： 本来加入多个组的话资金就会分散， 没有多少人愿意这么干， 但是先要找到这样的通路， 必须得有人自愿加入多个组， 2: 处于锁定状态的资金是不会被对方承认的， 所以找通路的时候可能路是通了， 但是路上某个组的资金被抽干了， 路就变的不同了， 解决办法给自愿付出的小伙伴一定的手续费


### 实现的原理
1. 请先阅读 [What is the Raiden Network?](https://raiden.network/101.html)
2. ##### 合约的类图
</br>

![plugin-pic](imgs/smart_contract_obj.png)

</br>

### 为什么需要channel 
... 在通道内转账的direct_transfer或者利用通道转账的mediated_transfer质押的资金只能花费一次， 因为每笔资金只能流向一个方向， 就是通道内伙伴


### 优化建议
+ channel状态的可以支持使用双方签名的状态修改操作, 比如提现操作channel内的双反都签名后就直接转账、关闭通道即可
+ 注册在 EndpointRegisty 节点可以作为p2p 的种子节点， 如此routing可以采用kademlia算法

### 基本架构
雷电网络四个服务构成
1. blochchain service : 用于和blockchain 交互， 例如获取 netting-channel-info, node的（host, port）等信息， 发送transaction(例如withdraw, close, deposit等), blockchain 主要由俩部分构成 eth_client（和链上交互的实体）、proxies(contract在本地的代理， 方便调用)、注册的filter以及相应的event msg 的 devoder
2. raiden service : 转账操作的实体， 由俩部分构成 transport（目前是UDP）：发送线下交易的实体、NodeState：这部分包含 storage（记录routing gragh、balance proof、locked transfer、token networking）, handler例如 handler_direct_transfer（partner线下转账）, handler_new_balance（partner在contract新增一笔押金）, handler_block（blocknum增加了， locked_transfer 是否还安全否则需要关闭channel去体现了）等
3. http service : 接受处理转账等http 请求
4. alarm service: 不断的获取最新的blocknum后执行注册的callback list 



### 交易的最简流程 
+ sendTransaction(create netting channel)
+ 在alarmService处注册监听netting_channel 的事件的handler: poll_netting_channel_event， poll的具体步骤blockchain_service.eth_client.filter（from, to, netting_channel_address）)
+ sendTransaction(channel.deposit)
+ alarmService poll blocknum后调用注册的callback
+ raiden_service.handler_channel_new_deposit(event)其结果是给对方账户上加钱 
+ curl httpserver.direct_transfer
+ httpserver调用raiden_service.direct_transfer  
+ transport.send
+ 接收方raiden_service.handler_direct_transfer


### A给B的最大可转账金额
```python

class Store:
    nodeId_to_transfer_amount = {}
    nodeId_to_balance = {}
    
    @classmethod
    def set_transfer_amount(cls, addr, transfer_amount):
         prefix = "transfer-amount:"  
         key = "{}-{}".format(prefix, addr)
         party = nodeId_to_transfer_amount.get(key, None)
         if party:
              nodeId_to_transfer_amount[key] = balance
    
    @classmethod          
    def get_transfer_amount(cls, addr):
        prefix = "transfer-amount:"  
        key = "{}-{}".format(prefix, addr)
        return nodeId_to_transfer_amount.get(key, 0)
    
    @classmethod    
    def get_deposit(cls, addr):
        prefix = "balance:"
        key = "{}-{}".format(prefix, addr)
        return nodeId_to_balance.get(key, ())
        
    @classmethod
    def set_deposit(cls, addr, value, blocknum):
        v = (value, blocknum)
        prefix = "balance:"
        key = "{}-{}".format(prefix, addr)
        nodeId_to_balance[key] = v
    
    @classmethod
    def get_endport(cls, addr):
        prefix = "endpoint:"
        key = "{}{}".format(prefix, addr)
        return endpoint.get(key, "")
    
    @classmethod
    def set_endport(addr, host_port):
        prefix = "endpoint:"
        key = "{}{}".format(prefix, addr)
        return endpoint.set(key, host_addr)
        
def get_balance(sender, receiver): 
    return  sender的质押金额 - 转出去的金额 + 收到的金额
def get_amount_locked(end_state):
    return 所有解锁了的锁定金额 + 所有锁定的金额    
def get_distributable(sender, receiver): // sender的可转账资金
    return get_balance(sender, receiver) - get_amount_locked(sender)
    
```

### direct transfer 的模拟过程
```python

q = Queue()
not_stop = True
transport = UdpServer(127.0.0.1, 33456)
class UdpServer:
    def __init__(self):
         self._server = DatagramServer(host, port, self._receive)
    def _receive(self, data, host):
         msg = decode(data)
         if msg["type"] = "ping":
              pass
         elif msg["type"] = "received":
              pass
         elif msg["type"] = "direct_transfer":
              handle_direct_transfer(msg)
    def send(self, msg, receiver):
         self._server.sentTo(msg, receiver)  
     
def sending(blocking=True)
    def runner():
        while not_stop:
            pair = q.peek(blocking):
            if pair:
                signed_msg = sign(pair[0])
                transport.send(signed_msg, pair[1])
                q.get()
            else:
                sleep()
    run_at_new_thread(runner)

def async_send_msg(msg):
    q.put(msg)

def transfer_direct(amount, receiver):
   available_amount = get_distributable(nodeId, receiver)
   if available_amount >= amount:
       msg = create_balance_proof(value)
       host_port = Store.get_endport(receiver, "")
       if host_port:
           async_send_msg((msg, host_port))
       return "ok"
   return "found not not available"   
   
def handler_direct_transfer(sender, msg):
    varify(msg) // 验证签名
    available_amount = get_distributable(sender, nodeId)
    if available_amount > msg['amount']:
         return "{}转账， 但是资金不足".format(sender)
    last_transfer_amount = Store.get_transfer_amount(sender)
    if last_transfer_amount>=msg["transfer_amount"]:
         return "{}非法请求".format(sender)
    Store.set_transfer_amount(sender, msg["amount"])     
    return "收到{}转账{}".format(sender, msg["amount"]-last_transfer_amount)
    
def create_balance_proof(value):  
    nonce = get_nonce()
    transfered_amount = Store.get_transfer_amount(nodeId)
    locked_root = get_loocked_root()
    msg = encode(value, nonce, locked_root)
    data = {"hash":hash(msg), "nonce":nonce, "amount":transfered_amount+amount, "locked_root":locked_root, "type":"direct_transfer"}}
    Store.set_transfer_amount(nodeId, transfered_amount+amount)
    return data

sending()
transfer_direct(10, receiver)

```


### blockchain event的处理流程（处理同一个channel内的countpanty deposit事件）
```python

nodeId = hash("self pub key")
event_callbacks= []

def decode(msg):
    if msg.topic == "channel_new_balance":
         return {"token":"resp from web3", balance:1, party:"resp from web3"} 
    return {}
    
def poll_contract_new_balance(from, to, channel_addr):
    events = eth.filter({from, to, addr})
    for event in events:
        msg = decode(event) 
        if msg["topic"] = "new_deposit":
             handle_new_deposit(msg["sender"], msg["value"], blocknum)

def is_safe_transaction(blocknum):
    return True if blocknum + 5 < current_blocknum else False         

def handler_new_deposit(sender, value, blocknum):
    while is_safe_transaction(blocknum):
         break
    v = Store.get_deposit(sender)
    if v[1] >= blocknum:
         //log("本地存储的数据和blockchain 上的数据冲突， 本地记录 在{}块 deposit:{}, blockchain:{}块deposit:{}".format{v[0], v[1], blocknum, value})
         exit("-1")
    Store.set_deposit(sender, value, blocknum)
    return "ok"

def reg_callbacks(cb):
    event_callbacks.append(cb)

def alarm():
   current_block_blocknum = snap.current_blocknum
   while True:
        num = poll_block_num()
        if num > current_block_blocknum:
              run_at_new_thread(event_callbacks)
        sleep(0.5)
reg_callbacks(poll_contract_new_balance) 
alarm()

```

