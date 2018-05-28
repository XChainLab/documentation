### 为什么使用 raiden-network 
1. 小额高频交易
2. 支持ERC20token交易

### 基本架构
... 雷电网络四个服务构成
1. blochchain service : 用于和blockchain 交互， 例如获取 netting-channel-info, node的（host, port）等信息， 发送transaction(例如withdraw, close, deposit等), blockchain 主要由俩部分构成 eth_client（和链上交互的实体）、proxies(contract在本地的代理， 方便调用)、注册的filter以及相应的event msg 的 devoder
2. raiden service : 转账操作的实体， 由俩部分构成 transport（目前是UDP）：发送线下交易的实体、NodeState：这部分包含 storage（记录routing gragh、balance proof、locked transfer、token networking）, handler例如 handler_direct_transfer（partner线下转账）, handler_new_balance（partner在contract新增一笔押金）, handler_block（blocknum增加了， locked_transfer 是否还安全否则需要关闭channel去体现了）等
3. http service : 接受处理转账等http 请求
4. alarm service: 不断的获取最新的blocknum后执行注册的callback list 

### 实现的原理
1. 请先阅读 [What is the Raiden Network?](https://raiden.network/101.html)
2. ##### 合类图
</br>

![plugin-pic](imgs/smart_contract_obj.png)

</br>

3. 交易的最简流程 
+ sendTransaction(create netting channel)
+ 在alarmService处注册监听netting_channel 的事件的handler: poll_netting_channel_event， poll的具体步骤blockchain_service.eth_client.filter（from, to, netting_channel_address）)
+ sendTransaction(channel.deposit)
+ alarmService poll blocknum后调用注册的callback
+ raiden_service.handler_channel_new_deposit(event)其结果是给对方账户上加钱 
+ curl httpserver.direct_transfer
+ httpserver调用raiden_service.direct_transfer  
+ transport.send
+ raiden_service.handler_direct_transfer


### A给B的最大可转账金额
```python

class Store:
    nodeId_to_transfer_amount = {}
    nodeId_to_balance = {}
    @classmethod
    def set_transfer_amount(addr, transfer_amount):
         prefix = "transfer-amount:"  
         key = "{}-{}".format(prefix, addr)
         party = nodeId_to_transfer_amount.get(key, None)
         if party:
              nodeId_to_transfer_amount[key] = balance
    @classmethod          
    def get_transfer_amount(addr):
        prefix = "transfer-amount:"  
        key = "{}-{}".format(prefix, addr)
        return nodeId_to_transfer_amount.get(key, 0)
    @classmethod    
    def get_deposit(addr):
        prefix = "balance:"
        key = "{}-{}".format(prefix, addr)
        return nodeId_to_balance.get(key, ())
        
    @classmethod
    def set_deposit(addr, value, blocknum):
        v = (value, blocknum)
        key = "{}-{}".format(prefix, addr)
        nodeId_to_balance[key] = v
        
def get_balance(sender, receiver): 
    return  sender的质押金额 - 转出去的金额 + 收到的金额
def get_amount_locked(end_state):
    return 所有解锁了的锁定金额 + 所有锁定的金额    
def get_distributable(sender, receiver): // sender的可转账资金
    return get_balance(sender, receiver) - get_amount_locked(sender)
    
```

### direct_transfer
```python

q = Queue()
not_stop = True
transport = UdpServer
class UdpServer:
    def __init__(self):
         self._server = DatagramServer(host, port, self.receive)
    def receive(self, data, host):
         msg = decode(data)
         if msg["type"] = "ping":
              pass
         elif msg["type"] = "received":
              pass
         elif msg["type"] = "direct_transfer":
              handle_direct_transfer(msg)
     
def sending(blocking=True)
    def runner():
        while not_stop:
            msg = q.peek(blocking):
            if msg:
                signed_msg = sign(msg)
                self._server.send(signed_msg)
                q.get()
            else:
                sleep()
    run_at_new_thread(runner)

def send_msg(msg):
    q.put(msg)

def transfer_direct(amount, receiver):
   available_amount = get_distributable(nodeId, receiver)
   if available_amount >= amount:
       msg = create_balance_proof(value)
       send_msg(msg)
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
    locked_root = get_loocked_root()
    msg = encode(value, nonce, locked_root)
    data = {"hash":hash(msg), "nonce":nonce, "amount":amount, "locked_root":locked_root, type:"direct_transfer"}}
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

