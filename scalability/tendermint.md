##### tendermint 使用 BFT-Like 共识算法出块， 本文将阐述其实现中一些技巧
1. proposer 将要block 拆分为proposal 和 parts, 拆分算法可简单归结为如下
+ _序列化Block， 获取hash值， proposal的主体内容有 block_hash、height(投票高度), round（当前高度下第几轮投票）_ 
+ _将序列化的block拆分为[][]byte数组_
+ _依据以上数组创建merkel tree_
+ _依据叶子节点及其merkel proof创建part, merkel proof 可归结使用叶子节点及其叔父节点推导祖父节点的重复过程直至推导出root节点

拆分的作用解释
+ _节点之间可以相互同步part， 完整性验证可由merkel proof 保证， 避免了消息下发中心化的问题_
+ _第二、三轮的投票仅需proposal头部即可， 消息体尺寸极大的降低了_ 

2. 通过维护远程节点的镜像来同步Message， 实现过程是：在于远程节点连接后，本地节点开启三个同步Routine及一个订阅了本地事件消息的broker来维持节点间的消息同步
+ _gossipDataRoutine负责block、tx、proposal同步_
+ _gossipVoteRoutine负责vote转发， 作用有二： 1发现BFT节点， 2加快出块（原因有二：1消息是SignedMessage， 所以我们无需担心篡改的问题， 2我们只关心超过2/3正直的节点做出了选择即可发起下一轮投票或者saveBlock）_
+ _gossipMaj23Routine同步投票镜像，为VoteRoutine同步投票提供依据_
+ _消息broker订阅EventRoundStep、EventVote、 EventProposalHeartbeat， 其处理都是将相应的消息广播给远程节点， 用以维护本地节点在远程的镜像， 以维持消息同步_

3. 通过scheduleTimeout来简化投票超时的实现过程， 算法实现如下
```raw
type timeoutInfo struct {
    Duration time.Duration         `json:"duration"`
    Height   int64                 `json:"height"`
    Round    int                   `json:"round"`
    Step     cstypes.RoundStepType `json:"step"`
}
tickChan = make(chan timeoutInfo, BufSize)
tockChan = make(chan timeoutInfo, BufSize)
timer = time.Timer
func scheduleTimeout(t *timeoutInfo){
    tickChan <- t
}
func (self timeoutInfo)newer(other timeoutInfo)bool{
    if self.Height < other.Height {
         return false
    } else if newti.Height == ti.Height {
        if self.Round < other.Round {
        	return false
        } else if self.Round == other.Round {
            if self.Step > 0 && self.Step <= other.Step {
                return false
            }
        }
    }
    return true
}
func timeoutRoutine() {
    var ti timeoutInfo
    for {
        select {
        case newti := <-tickChan:
            if ！newti.newer(ti){
                continue
            }
            timer.Stop()
            ti = newti
            timer.Reset(ti.Duration)
        case <-timer.C:
            go func(toi timeoutInfo) { t.tockChan <- toi }(ti)
        case <- quit():
            return
    }
}
func someRoutinue(){
    for{
        select{
        case t := <- tockChan:
            go handleTimeout(t)
        ......
        }
    }
}

func handleTimeout(t timeoutInfo){
    ....
    ....
}
```

4. 通过状态机转换来简化投票过程， 主要三个状态是proposal、prevote、precommit、以及主要状态各自对应的wait状态、另外在加开始的俩个状态NewHeight、NewRound以及结束的commit状态共计九个状态， 状态转换图如下
```raw

                                +-------------------------------------+
                                v                                     |(Wait til `CommmitTime+timeoutCommit`)
                          +-----------+                         +-----+-----+
             +----------> |  Propose  +--------------+          | NewHeight |
             |            +-----------+              |          +-----------+
             |                                       |                ^
             |(Else, after timeoutPrecommit)         v                |
       +-----+-----+                           +-----------+          |
       | Precommit |  <------------------------+  Prevote  |          |
       +-----+-----+                           +-----------+          |
             |(When +2/3 Precommits for block found)                  |
             v                                                        |
       +--------------------------------------------------------------------+
       |  Commit                                                            |
       |                                                                    |
       |  * Set CommitTime = now;                                           |
       |  * Wait for block, then stage/save/commit block;                   |
       +--------------------------------------------------------------------+


```

5. 通过wal机制保证断点恢复， 状态转换前先write转换参数， 恢复时只需逐层load转换参数即可。

6. 惩罚BFT节点的算法
```raw
  1. 开始Block高度为H的投票
  2. 本地节点收到节点A的投票，将投票加入本地VoteSet集合 
  3. 收到节点B发来节点A的投票， 该投票与本地VoteSet中的投票冲突
  4. 将冲突证据加入EvidencePool并广播证据
  5. 高度为H的投票结束，开始执行BLock中Transaction并且依据Block的Evidence惩罚BFT节点， 开始H+1 的投票
  6. proposer创建高度为H+1 Block, 将收到的冲突证据加入到Block中
  7. 开始 2～5
```  

