# khipu并行分析之二状态和上下文

## 1、并行的状态控制
并行的状态控制主要有两个一个是WorldState.scala,另外一个是BlockWorldState.scala。从形式上来看二者是组合的关系，但实际应该是依赖或者实现的关系，不太明白Scala的用法。
</br>

```
object BlockWorldState {

  sealed trait RaceCondition
  case object OnAddress extends RaceCondition
  case object OnAccount extends RaceCondition
  case object OnStorage extends RaceCondition
  case object OnCode extends RaceCondition
  ......
  def apply(
  blockchain:         Blockchain,
  accountNodeStorage: NodeKeyValueStorage,
  storageNodeStorage: NodeKeyValueStorage,
  accountStartNonce:  UInt256,
  stateRootHash:      Option[Hash]        = None
): BlockWorldState = {

  /**
   * Returns an accounts state trie "The world state (state), is a mapping
   * between Keccak 256-bit hashes of the addresses (160-bit identifiers) and account states
   * (a data structure serialised as RLP [...]).
   * Though not stored on the blockchain, it is assumed that the implementation will maintain this mapping in a
   * modified Merkle Patricia tree [...])."
   *
   * See [[http://paper.gavwood.com YP 4.1]]
   */
  val underlyingAccountsTrie = MerklePatriciaTrie[Address, Account](
    stateRootHash.getOrElse(Hash(trie.EmptyTrieHash)).bytes,
    accountNodeStorage
  )(Address.hashedAddressEncoder, Account.accountSerializer)

  new BlockWorldState(
    blockchain,
    accountNodeStorage,
    storageNodeStorage,
    accountStartNonce,
    blockchain.evmCodeStorage,
    TrieAccounts(underlyingAccountsTrie),
    Map(),
    Map(),
    Map(),
    Map(),
    Set(),
    None
  )
}
}
```
</br>
在他的下面是伴生类BlockWorldState
</br>

 ```
 final class BlockWorldState private (
     blockchain:                   Blockchain,
     accountNodeStorage:           NodeKeyValueStorage,
     storageNodeStorage:           NodeKeyValueStorage,
     accountStartNonce:            UInt256,
     evmCodeStorage:               EvmCodeStorage,
     private var trieAccounts:     TrieAccounts,
     private var trieStorages:     Map[Address, TrieStorage],
     private var codes:            Map[Address, ByteString],
     private var accountDeltas:    Map[Address, Vector[BlockWorldState.AccountDelta]],
     private var raceConditions:   Map[BlockWorldState.RaceCondition, Set[Address]],
     private var touchedAddresses: Set[Address], // for debug
     private var stx:              Option[SignedTransaction] // for debug
 ) extends WorldState[BlockWorldState, TrieStorage]
 ```
</br>
通过上面的类和它的伴生对象可以看出，竞态条件并不太多，只有四个，即OnAddress、OnAccount、OnStorage、OnCode。和前面的说明是呼应的，其实在合并状态时，重点还是关注前三个，Code在执行时就会进行处理。
</br>
在状态的类成员中，有大量的状态获取函数，用来从当前世界状态中取得当前的状态值。事务的回滚也是靠这些数据来实现的，同时，由于只考虑记载当前交易状态，所以取消了对锁的控制。

## 2、并行的上下文
并行的上下文主要有两个类：
</br>

```
object ProgramState {
  trait ParallelRace
  case object OnAccount extends ParallelRace
  case object OnError extends ParallelRace
}
/**
 * Intermediate state updated with execution of each opcode in the program
 *
 * @param context the context which initiates the program
 * @param gas current gas for the execution
 * @param stack current stack
 * @param memory current memory
 * @param pc program counter - an index of the opcode in the program to be executed
 * @param returnData data to be returned from the program execution
 * @param gasRefund the amount of gas to be refunded after execution (not sure if a separate field is required)
 * @param addressesToDelete list of addresses of accounts scheduled to be deleted
 * @param halted a flag to indicate program termination
 * @param error indicates whether the program terminated abnormally
 */
final class ProgramState[W <: WorldState[W, S], S <: Storage[S]](val context: ProgramContext[W, S], val isDebugTraceEnabled: Boolean) {
  import ProgramState._

  var gas: Long = context.startGas
  var world: W = context.world
  var addressesToDelete: Set[Address] = context.initialAddressesToDelete
  var addressesTouched: Set[Address] = context.initialAddressesTouched

  var pc: Int = 0
  var returnData: ByteString = ByteString()
  var gasRefund: Long = 0
  var txLogs: Vector[TxLogEntry] = Vector()
  private var _halted: Boolean = false
  var error: Option[ProgramError] = None
  private var _isRevert: Boolean = false

  var returnDataBuffer: ByteString = ByteString()

  private var _parallelRaceConditions = Set[ParallelRace]()

  val stack: Stack = Stack.empty()
  val memory: Memory = Memory.empty()

......

  def parallelRaceConditions = _parallelRaceConditions
  def withParallelRaceCondition(race: ParallelRace) = {
    this._parallelRaceConditions +=
    this
  }
  def mergeParallelRaceConditions(races: Set[ParallelRace]) = {
    this._parallelRaceConditions ++= racesrace
    this
  }

......
}
```
</br>
另外一个是程序的上下文：
</br>

```
object ProgramContext {
  def apply[W <: WorldState[W, S], S <: Storage[S]](
    stx:                      SignedTransaction,
    recipientAddress:         Address,
    program:                  Program,
    blockHeader:              BlockHeader,
    world:                    W,
    config:                   EvmConfig,
    initialAddressesToDelete: Set[Address],
    initialAddressesTouched:  Set[Address],
    isStaticCall:             Boolean
  ): ProgramContext[W, S] = {

    // YP eq (91)
    val inputData = if (stx.tx.isContractCreation) ByteString() else stx.tx.payload

    val env = ExecEnv(
      recipientAddress,
      stx.sender,
      stx.sender,
      stx.tx.gasPrice,
      inputData,
      stx.tx.value,
      program,
      blockHeader,
      callDepth = 0
    )

    val startGas = stx.tx.gasLimit - config.calcTransactionIntrinsicGas(stx.tx.payload, stx.tx.isContractCreation)

    ProgramContext(env, recipientAddress, startGas, world, config, initialAddressesToDelete, initialAddressesTouched, isStaticCall)
  }
}

/**
 * Input parameters to a program executed on the EVM. Apart from the code itself
 * it should have all (interfaces to) the data accessible from the EVM.
 *
 * @param env set of constants for the execution
 * @param targetAddress used for determining whether a precompiled contract is being called (potentially
 *                      different from the addresses defined in env)
 * @param startGas initial gas for the execution
 * @param world provides interactions with world state
 * @param config evm config
 * @param initialAddressesToDelete contains initial set of addresses to delete (from lower depth calls)
 */
final case class ProgramContext[W <: WorldState[W, S], S <: Storage[S]](
  env:                      ExecEnv,
  targetAddress:            Address,
  startGas:                 Long,
  world:                    W,
  config:                   EvmConfig,
  initialAddressesToDelete: Set[Address],
  initialAddressesTouched:  Set[Address],
  isStaticCall:             Boolean
)
```
</br>
这两个类互相扶持，掌握着程序的上下文的状态，可以从其中得到世界状态，或者这样说，通过programstate来进行程序和并行交易的控制，包括并行的数量设置，都在这个类中。
</br>

## 3、并行状态和上下文的更新和合并
状态和上下文结合后，开始在两个地方进行处理，一个是VM，一个是Ledger中。基本上就是在执行区块这个函数命令中，来回穿梭调用两个相关的依赖对象。
</br>

```
case object BALANCE extends OpCode[UInt256](0x31, 1, 1) with ConstGas[UInt256] {
  protected def constGasFn(s: FeeSchedule) = s.G_balance
  protected def getParams[W <: WorldState[W, S], S <: Storage[S]](state: ProgramState[W, S]) = {
    val List(accountAddress) = state.stack.pop()
    accountAddress
  }

  protected def exec[W <: WorldState[W, S], S <: Storage[S]](state: ProgramState[W, S], params: UInt256): ProgramState[W, S] = {
    val accountAddress = params
    val accountBalance = state.world.getBalance(Address(accountAddress))
    state.stack.push(accountBalance)
    state.withParallelRaceCondition(ProgramState.OnAccount).step()
  }
}
```
</br>
</br>
合并在块状态中的代码：
</br>

```
private[ledger] def commit(): BlockWorldState = {
   trieAccounts = trieAccounts.commit()
   this
 }

 /**
  * Should be called adter committed
  */
 def persist(): BlockWorldState = {
   // deduplicate codes first
   this.codes.foldLeft(Map[Hash, ByteString]()) {
     case (acc, (address, code)) => acc + (Hash(crypto.kec256(code)) -> code)
   } foreach {
     case (hash, code) => evmCodeStorage + (hash -> code)
   }

   this.trieStorages.foreach {
     case (address, storageTrie) => storageTrie.underlying.persist()
   }

   this.trieAccounts.underlying.persist()

   this
 }

 // --- merge ---

 def mergeRaceConditions(later: BlockWorldState): BlockWorldState = {
   later.raceConditions foreach {
     case (k, vs) => this.raceConditions += (k -> (this.raceConditions.getOrElse(k, Set()) ++ vs))
   }
   this
 }

 private[ledger] def merge(later: BlockWorldState): Either[Map[RaceCondition, Set[Address]], BlockWorldState] = {
   val raceCondiftions = this.raceConditions.foldLeft(Map[RaceCondition, Set[Address]]()) {
     case (acc, (OnAccount, addresses)) => acc + (OnAccount -> addresses.filter(later.trieAccounts.logs.contains))
     case (acc, (OnStorage, addresses)) => acc + (OnStorage -> addresses.filter(later.trieStorages.contains))
     case (acc, (OnCode, addresses))    => acc + (OnCode -> addresses.filter(later.codes.contains))
     case (acc, (OnAddress, addresses)) => acc + (OnAddress -> addresses.filter(x => later.codes.contains(x) || later.trieStorages.contains(x) || later.trieAccounts.logs.contains(x)))
   } filter (_._2.nonEmpty)

   if (raceCondiftions.isEmpty) {
     val toMerge = this.copy
     toMerge.touchedAddresses ++= later.touchedAddresses
     //mergeAccountTrieAccount_simple(toMerge, that)
     toMerge.mergeAccountTrieAccount(later).mergeTrieStorage(later).mergeCode(later).mergeRaceConditions(later)
     Right(toMerge)
   } else {
     Left(raceCondiftions)
   }
 }

 /** mergeAccountTrieAccount should work now, mergeAccountTrieAccount_simple is left here for reference only */
 private def mergeAccountTrieAccount_simple(later: BlockWorldState): BlockWorldState = {
   this.trieAccounts.logs ++= later.trieAccounts.logs
   this
 }

 private def mergeAccountTrieAccount(later: BlockWorldState): BlockWorldState = {
   val alreadyMergedAddresses = later.accountDeltas map {
     case (address, deltas) =>
       val valueMerged = deltas.foldLeft(this.getAccount(address).getOrElse(this.emptyAccount)) {
         case (acc, AccountDelta(nonce, balance, _, _)) => acc.increaseNonce(nonce).increaseBalance(balance)
       }

       // just put the lasted stateRoot and codeHash of y and merge delete
       later.trieAccounts.logs.get(address).map {
         case Updated(Account(_, _, stateRoot, codeHash)) => this.trieAccounts += (address -> valueMerged.withStateRoot(stateRoot).withCodeHash(codeHash))
         case Original(_)                                 => this.trieAccounts += (address -> valueMerged)
         case Deleted(_)                                  => this.trieAccounts -= address
       }

       address
   } toSet

   this.trieAccounts.logs ++= (later.trieAccounts.logs -- alreadyMergedAddresses)
   this
 }

 private def mergeTrieStorage(later: BlockWorldState): BlockWorldState = {
   this.trieStorages ++= later.trieStorages
   this
 }

 private def mergeCode(later: BlockWorldState): BlockWorldState = {
   this.codes ++= later.codes
   this
 }
```
</br>
merge函数里首先根据竞态条件依次进行合并处理，然后再合并相关状态树等。这也和最初提出的三个方向基本保持一致。这个合并函数在并行执行结果处被调用
</br>

```
prevWorld.merge(txResult.world) match {
  case Left(raceCondiftions) =>
    log.debug(s"tx ${txResult.stx.hash} has race conditions with prev world state:\n$raceCondiftions")
    reExecute(txResult.stx, prevWorld)

  case Right(mergedWorld) =>
    parallelCount += 1
    currWorld = Some(mergedWorld)
    txResults = txResults :+ txResult
}
```
</br>
涉及到一个问题，就是Reward的计算，处理它使用了类似的机制，分三步进行：
</br>
1、预计算
</br>

```
override def prepareBlock(
  block:      Block,
  validators: Validators
)(implicit executor: ExecutionContext): Future[BlockPreparationResult] = {
  val parentStateRoot = blockchain.getBlockHeaderByHash(block.header.parentHash).map(_.stateRoot)
  val initialWorld = blockchain.getReadOnlyWorldState(None, blockchainConfig.accountStartNonce, parentStateRoot)

  executePreparedTransactions(block.body.transactionList, initialWorld, block.header, validators.signedTransactionValidator) map {
    case (execResult @ BlockResult(resultingWorldState, _, _, _), txExecuted) =>
      val worldRewardPaid = payBlockReward(block)(resultingWorldState)
      val worldPersisted = worldRewardPaid.commit().persist()
      BlockPreparationResult(block.copy(body = block.body.copy(transactionList = txExecuted)), execResult, worldPersisted.stateRootHash)
  }
}
```
</br>
2、执行中计算
</br>

```
override def executeBlock(block: Block, validators: Validators)(implicit executor: ExecutionContext): Future[Either[BlockExecutionError, BlockResult]] = {
  val start1 = System.nanoTime
  val parallelResult = executeBlockTransactions(block, validators.signedTransactionValidator, isParallel = true && !blockchainConfig.isDebugTraceEnabled) map {
    case Right(blockResult) =>
      log.debug(s"${block.header.number} parallel-executed in ${(System.nanoTime - start1) / 1000000}ms")

      val start2 = System.nanoTime
      val worldRewardPaid = payBlockReward(block)(blockResult.world)
    }
    ......
}
```
</br>
3、并行结果后计算
</br>

```
parallelResult flatMap {
  case Right((blockResult, worldCommitted)) => Future.successful(Right(blockResult))

  case left @ Left(error) =>
    log.debug(s"in parallel failed with error $error, try sequential ...")

    val start1 = System.nanoTime
    executeBlockTransactions(block, validators.signedTransactionValidator, isParallel = false) map {
      case Right(blockResult) =>
        log.debug(s"${block.header.number} sequential-executed in ${(System.nanoTime - start1) / 1000000}ms")

        val worldRewardPaid = payBlockReward(block)(blockResult.world)
      }
  }
```
</br>
4、计算函数
</br>

```
private def payBlockReward(block: Block)(world: BlockWorldState): BlockWorldState = {
  val minerAddress = Address(block.header.beneficiary)
  val minerAccount = getAccountToPay(minerAddress)(world)
  val minerReward = blockRewardCalculator.calcBlockMinerReward(block.header.number, block.body.uncleNodesList.size)
  val afterMinerReward = world.saveAccount(minerAddress, minerAccount.increaseBalance(minerReward))
  log.debug(s"Paying block ${block.header.number} reward of $minerReward to miner with account address $minerAddress")

  block.body.uncleNodesList.foldLeft(afterMinerReward) { (ws, ommer) =>
    val ommerAddress = Address(ommer.beneficiary)
    val account = getAccountToPay(ommerAddress)(ws)
    val ommerReward = blockRewardCalculator.calcOmmerMinerReward(block.header.number, ommer.number)
    log.debug(s"Paying block ${block.header.number} reward of $ommerReward to ommer with account address $ommerAddress")
    ws.saveAccount(ommerAddress, account.increaseBalance(ommerReward))
  }
}
```
</br>
5、最终给付
</br>

```
private def postExecuteTransactions(
  blockHeader: BlockHeader,
  evmCfg:      EvmConfig,
  txResults:   Vector[TxResult],
  stats:       Stats
)(world: BlockWorldState): Either[BlockExecutionError, BlockResult] = {
  try {
    val (accGas, accTxFee, accTouchedAddresses, accReceipts) = txResults.foldLeft(0L, UInt256.Zero, Set[Address](), Vector[Receipt]()) {
      case ((accGas, accTxFee, accTouchedAddresses, accReceipts), TxResult(stx, worldAfterTx, gasUsed, txFee, logs, touchedAddresses, _, error, isRevert, _)) =>

        val postTxState = if (evmCfg.eip658) {
          if (error.isDefined || isRevert) Receipt.Failure else Receipt.Success
        } else {
          worldAfterTx.stateRootHash
          //worldAfterTx.commit().stateRootHash // TODO here if get stateRootHash, should commit first, but then how about parallel running? how about sending a lazy evaulate function instead of value?
        }

        log.debug(s"Tx ${stx.hash} gasLimit: ${stx.tx.gasLimit}, gasUsed: $gasUsed, cumGasUsed: ${accGas + gasUsed}")

        val receipt = Receipt(
          postTxState = postTxState,
          cumulativeGasUsed = accGas + gasUsed,
          logsBloomFilter = BloomFilter.create(logs),
          logs = logs
        )

        (accGas + gasUsed, accTxFee + txFee, accTouchedAddresses ++ touchedAddresses, accReceipts :+ receipt)
    }

    //计算并给付GAS
    val minerAddress = Address(blockHeader.beneficiary)
    val worldPayMinerForGas = world.pay(minerAddress, accTxFee)

    // find empty touched accounts to be deleted
    val deadAccounts = if (evmCfg.eip161) {
      (accTouchedAddresses + minerAddress) filter (worldPayMinerForGas.isAccountDead)
    } else {
      Set[Address]()
    }
    //log.debug(s"touched accounts: ${result.addressesTouched}, miner: $minerAddress")
    log.debug(s"dead accounts accounts: $deadAccounts")
    val worldDeletedDeadAccounts = deleteAccounts(deadAccounts)(worldPayMinerForGas)

    log.debug(s"$blockHeader, accGas $accGas, receipts = $accReceipts")
    Right(BlockResult(worldDeletedDeadAccounts, accGas, accReceipts, stats))
  } catch {
    case MPTNodeMissingException(_, hash, table) => Left(MissingNodeExecptionError(blockHeader.number, hash, table))
    case e: Throwable                            => throw e
  }
}
```
</br>
最终更新到世界状态中做为下一次区块并行交易的起点状态。

## 4、总结
通过上面的分析发现，khipu的并行思路不错，简单有效，而且基于目前网络上真正能够冲突的数据还是比较少的实际环境，提高的速度还是比较明显的。在下一篇，详细分析并行的过程。
