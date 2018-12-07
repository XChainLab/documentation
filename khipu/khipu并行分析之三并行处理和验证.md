# khipu并行分析之三并行处理和验证

## 一、并行的启动
并行的处理从两个阶段展开，一个是自己挖矿成功时对交易的并行处理（这里需要注意的是准备块时的预执行是串行的）；另外一个就是在接收到其它节点传播过来的块时进行的并行交易处理。在前面提到过，在khipu中是并行交易分别存储状态，然后在合并状态时串行操作。这样的好处是：增加了并行的速度，不使用锁安全性会有所增强，而且状态的合并本身并不是耗时的重点，所以基本上不会形成瓶颈。
</br>
优点明显，缺点也比较明显，所有的验证放到最后，那么如果交易冲突较多时，反而会引起性能的下降，不过针对公网的交易，冲突项还是相对较小的，以他们自己的测试来看，应该有三到五倍的提高。按照其文档说明，优势最容易体现出来的是可以使用机械硬盘进行全节点的同步。
</br>
这里不是分析网络同步，所以会直接深入到块的并行交易处进行分析。

## 二、并行的处理

## 1、并行的执行
挖矿开始：
</br>

```
// TODO improve mined block handling - add info that block was not included because of syncing [EC-250]
// we allow inclusion of mined block only if we are not syncing / reorganising chain
private def processMinedBlock(block: Block) {
  if (workingHeaders.isEmpty && !isRequesting) {
    // we are at the top of chain we can insert new block
    blockchain.getTotalDifficultyByHash(block.header.parentHash) match {
      case Some(parentTd) if block.header.number > appStateStorage.getBestBlockNumber =>
        // just insert block and let resolve it with regular download
        //此处开始并行调用
        val f = executeAndInsertBlock(block, parentTd, isBatch = false) andThen {
          case Success(Right(newBlock)) =>
            // broadcast new block
            handshakedPeers foreach {
              case (peerId, (peer, peerInfo)) => peer.entity ! PeerEntity.MessageToPeer(peerId, newBlock)
            }

          case Success(Left(error)) =>

          case Failure(e)           =>
        }
        Await.result(f, Duration.Inf)
      case _ =>
        log.error("Failed to add mined block")
    }
  } else {
    ommersPool ! OmmersPool.AddOmmers(List(block.header))
  }
}
```
</br>
接收其它区块开始：
</br>

```
//doProcessBlockBodies同样会调用
private def executeAndInsertBlocks(blocks: Vector[Block], parentTd: UInt256, isBatch: Boolean): Future[(UInt256, Vector[NewBlock], Vector[BlockExecutionError])] = {
  blocks.foldLeft(Future.successful(parentTd, Vector[NewBlock](), Vector[BlockExecutionError]())) {
    case (prevFuture, block) =>
      prevFuture flatMap {
        case (parentTotalDifficulty, newBlocks, Vector()) =>
         //此处与挖矿一样调用同一函数，注意二者不同
          executeAndInsertBlock(block, parentTotalDifficulty, isBatch) map {
            case Right(newBlock) =>
              // reset lookbackFromBlock only when executeAndInsertBlock success
              lookbackFromBlock = None

              // check blockHashToDelete
              blockchain.getBlockHeaderByNumber(block.header.number).map(_.hash).filter(_ != block.header.hash) foreach blockchain.removeBlock

              (newBlock.totalDifficulty, newBlocks :+ newBlock, Vector())
            case Left(error) =>
              (parentTotalDifficulty, newBlocks, Vector(error))
          }

        case (parentTotalDifficulty, newBlocks, errors) =>
          Future.failed(ExecuteAndInsertBlocksAborted(parentTotalDifficulty, newBlocks, errors))
      }
  } recover {
    case ExecuteAndInsertBlocksAborted(parentTotalDifficulty, newBlocks, errors) =>
      (parentTotalDifficulty, newBlocks, errors)
  }
}
```
</br>
它们最终会调用execBlock中的executeBlockTransactions这个函数：
</br>

```
override def executeBlock(block: Block, validators: Validators)(implicit executor: ExecutionContext): Future[Either[BlockExecutionError, BlockResult]] = {
   val start1 = System.nanoTime
   //启动并行
   val parallelResult = executeBlockTransactions(block, validators.signedTransactionValidator, isParallel = true && !blockchainConfig.isDebugTraceEnabled) map {
     case Right(blockResult) =>
        ......
     case Left(error) => Left(error)
   }

   //处理并行结果，如果验证不通过，改做串行
   parallelResult flatMap {
     case Right((blockResult, worldCommitted)) => Future.successful(Right(blockResult))

     case left @ Left(error) =>
       log.debug(s"in parallel failed with error $error, try sequential ...")

       val start1 = System.nanoTime
       //重点在这里，最后一个布尔值变成了false,意味着串行
       executeBlockTransactions(block, validators.signedTransactionValidator, isParallel = false) map {
         case Right(blockResult) =>
              ......
           }

         case Left(error) => Left(error)
       }
   }
 }
private def executeBlockTransactions(
  block:        Block,
  stxValidator: SignedTransactionValidator,
  isParallel:   Boolean
)(implicit executor: ExecutionContext): Future[Either[BlockExecutionError, BlockResult]] = {
  val parentStateRoot = blockchain.getBlockHeaderByHash(block.header.parentHash).map(_.stateRoot)
  val evmCfg = EvmConfig.forBlock(block.header.number, blockchainConfig)

  def initialWorld = blockchain.getWorldState(block.header.number, blockchainConfig.accountStartNonce, parentStateRoot)

//在这里判断配置的是串行还是并行交易，并根据配置的数量进行并行
  if (isParallel) {
    executeTransactions_inparallel(block.body.transactionList, block.header, stxValidator, evmCfg)(initialWorld)
  } else {
    executeTransactions_sequential(block.body.transactionList, block.header, stxValidator, evmCfg)(initialWorld)
  }
}
```
</br>
下面是真正的并行函数：
</br>

```
private def executeTransactions_inparallel(
  signedTransactions: Seq[SignedTransaction],
  blockHeader:        BlockHeader,
  stxValidator:       SignedTransactionValidator,
  evmCfg:             EvmConfig
)(initialWorldFun: => BlockWorldState)(implicit executor: ExecutionContext): Future[Either[BlockExecutionError, BlockResult]] = {
  val nTx = signedTransactions.size
  //类似于这种计时统计可以忽略
  val start = System.nanoTime
  blockchain.storages.accountNodeDataSource.clock.start()
  blockchain.storages.storageNodeDataSource.clock.start()
  blockchain.storages.evmCodeDataSource.clock.start()
  blockchain.storages.blockHeaderDataSource.clock.start()
  blockchain.storages.blockBodyDataSource.clock.start()

  //并行从这里开始，形成future,并交给TxProcessor去执行，在每个TxProcessor中有一个Work，来进行交易的执行
  val fs = signedTransactions.map(stx => stx -> initialWorldFun.withTx(Some(stx))) map {
    case (stx, initialWorld) =>
      (txProcessor ? TxProcessor.ExecuteWork(initialWorld, stx, blockHeader, stxValidator, evmCfg))(txProcessTimeout).mapTo[(Either[BlockExecutionError, TxResult], Long)] // recover { case ex => s"$ex.getMessage" }
  }

  //并行执行
  Future.sequence(fs) map { rs =>
    val dsGetElapsed1 = blockchain.storages.accountNodeDataSource.clock.elasped + blockchain.storages.storageNodeDataSource.clock.elasped +
      blockchain.storages.evmCodeDataSource.clock.elasped + blockchain.storages.blockHeaderDataSource.clock.elasped + blockchain.storages.blockBodyDataSource.clock.elasped

    val cacheHitRates = List(blockchain.storages.accountNodeDataSource.cacheHitRate, blockchain.storages.storageNodeDataSource.cacheHitRate).map(_ * 100.0)

    //忽略
    blockchain.storages.accountNodeDataSource.clock.start()
    blockchain.storages.storageNodeDataSource.clock.start()
    blockchain.storages.evmCodeDataSource.clock.start()
    blockchain.storages.blockHeaderDataSource.clock.start()
    blockchain.storages.blockBodyDataSource.clock.start()

    val (results, elapses) = rs.unzip
    val elapsed = elapses.sum
    log.debug(s"${blockHeader.number} executed parallel in ${(System.nanoTime - start) / 1000000}ms, db get ${100.0 * dsGetElapsed1 / elapsed}%")

    var currWorld: Option[BlockWorldState] = None
    var txError: Option[BlockExecutionError] = None
    var txResults = Vector[TxResult]()
    var parallelCount = 0

    // re-execute tx under prevWorld, commit prevWorld to get all nodes exist, see BlockWorldState.getStorage and getStateRoott
    var reExecutedElapsed = 0L
    //定义一个重新执行的函数，有点类似c++的lambda
    def reExecute(stx: SignedTransaction, prevWorld: BlockWorldState) = {
      var start = System.nanoTime
      log.debug(s"${stx.hash} re-executing")
      // should commit prevWorld's state, since we may need to get newest account/storage/code by new state's hash
      //保存世界状态和结果
      validateAndExecuteTransaction(stx, blockHeader, stxValidator, evmCfg)(prevWorld.commit().withTx(Some(stx))) match {
        case Left(error) => txError = Some(error)
        case Right(newTxResult) =>
          currWorld = Some(newTxResult.world)
          txResults = txResults :+ newTxResult
      }
      reExecutedElapsed += System.nanoTime - start
    }

    val itr = results.iterator
    while (itr.hasNext && txError.isEmpty) {
      val r = itr.next()
      r match {
        case Right(txResult) =>
          currWorld match {
            case None => // first tx
              parallelCount += 1
              currWorld = Some(txResult.world)
              txResults = txResults :+ txResult

            case Some(prevWorld) =>
              if (txResult.parallelRaceConditions.nonEmpty) {
                log.debug(s"tx ${txResult.stx.hash} potential parallel race conditions ${txResult.parallelRaceConditions} occurred during executing")
                // when potential parallel race conditions occurred during executing, it's difficult to judge if it was caused by conflict, so, just re-execute
                reExecute(txResult.stx, prevWorld)
              } else {
                //合并世界状态
                prevWorld.merge(txResult.world) match {
                  case Left(raceCondiftions) =>
                    log.debug(s"tx ${txResult.stx.hash} has race conditions with prev world state:\n$raceCondiftions")
                    //再次执行
                    reExecute(txResult.stx, prevWorld)

                  case Right(mergedWorld) =>
                    parallelCount += 1
                    currWorld = Some(mergedWorld)
                    txResults = txResults :+ txResult
                }
              }
          }

        case Left(error @ TxsExecutionError(_, stx, _, SignedTransactionError.TransactionSenderCantPayUpfrontCostError(_, _))) =>
          currWorld match {
            case None => txError = Some(error) // first tx
            case Some(prevWorld) =>
              reExecute(stx, prevWorld)
          }

        case Left(error) => txError = Some(error)
      }

      //log.debug(s"${blockHeader.number} touched accounts (${r.fold(_.stx, _.stx).hash}):\n ${currWorld.map(_.touchedAccounts.mkString("\n", "\n", "\n")).getOrElse("")}")
    }

    val dsGetElapsed2 = blockchain.storages.accountNodeDataSource.clock.elasped + blockchain.storages.storageNodeDataSource.clock.elasped +
      blockchain.storages.evmCodeDataSource.clock.elasped + blockchain.storages.blockHeaderDataSource.clock.elasped + blockchain.storages.blockBodyDataSource.clock.elasped

    //忽略并行参数统计的计算
    val parallelRate = if (parallelCount > 0) {
      parallelCount * 100.0 / nTx
    } else {
      0.0
    }
    val dbReadTimePerc = 100.0 * (dsGetElapsed1 + dsGetElapsed2) / (elapsed + reExecutedElapsed)

    log.debug(s"${blockHeader.number} re-executed in ${reExecutedElapsed}ms, ${100 - parallelRate}% with race conditions, db get ${100.0 * dsGetElapsed2 / reExecutedElapsed}%")
    log.debug(s"${blockHeader.number} touched accounts:\n ${currWorld.map(_.touchedAccounts.mkString("\n", "\n", "\n")).getOrElse("")}")

    txError match {
      case Some(error) => Left(error)
      case None        => postExecuteTransactions(blockHeader, evmCfg, txResults, Stats(parallelCount, dbReadTimePerc, cacheHitRates))(currWorld.map(_.withTx(None)).getOrElse(initialWorldFun))
    }
  } andThen {
    case Success(_) =>
    case Failure(e) => log.error(e, s"Error on block ${blockHeader.number}: ${e.getMessage}")
  }
}
```
这样一个并行的处理就开始了。
</br>

## 2、并行的状态保存
在上面开始并行交易后，会发现，真正用来处理并行的是调用validateAndExecuteTransaction这个函数，调用这个函数的地方有两处，一处是前面提到的TxProcessor中，另外一处在reExecute中。因为后者其实是处理错误异常的情况，所以直接看前面的就可以，它会调用executeTransaction，同时会计算一下费用。
</br>

```
private def executeTransaction(
  stx:         SignedTransaction,
  blockHeader: BlockHeader,
  evmCfg:      EvmConfig
)(world: BlockWorldState): TxResult = {
  val start = System.nanoTime

  // TODO catch prepareProgramContext's throwable (MPTException etc from mtp) here
  val (checkpoint, context) = prepareProgramContext(stx, blockHeader, evmCfg)(world)

  if (blockchainConfig.isDebugTraceEnabled) {
    println(s"\nTx 0x${stx.hash} ========>")
  }

  //重点这里，会调用虚拟机，将交易执行
  val result = runVM(stx, context, evmCfg)(checkpoint)

  val gasLimit = stx.tx.gasLimit
  val totalGasToRefund = calcTotalGasToRefund(gasLimit, result)
  val gasUsed = stx.tx.gasLimit - totalGasToRefund
  val gasPrice = stx.tx.gasPrice
  val txFee = gasPrice * gasUsed
  val refund = gasPrice * totalGasToRefund

  if (blockchainConfig.isDebugTraceEnabled) {
    println(s"\nTx 0x${stx.hash} gasLimit: ${stx.tx.gasLimit} gasUsed $gasUsed, isRevert: ${result.isRevert}, error: ${result.error}")
  }

  val worldRefundGasPaid = result.world.pay(stx.sender, refund)
  val worldDeletedAccounts = deleteAccounts(result.addressesToDelete)(worldRefundGasPaid)

  val elapsed = System.nanoTime - start
  TxResult(stx, worldDeletedAccounts, gasUsed, txFee, result.txLogs, result.addressesTouched, result.returnData, result.error, result.isRevert, result.parallelRaceConditions)
}
private def runVM(stx: SignedTransaction, context: PC, evmCfg: EvmConfig)(checkpoint: BlockWorldState): PR = {
  val r = if (stx.tx.isContractCreation) { // create
    //真正的虚拟机执行
    VM.run(context, blockchainConfig.isDebugTraceEnabled)
  } else { // call
    //类似于以太坊的固有的合约
    PrecompiledContracts.getContractForAddress(context.targetAddress, evmCfg) match {
      case Some(contract) =>
        contract.run(context)//此处也会调用虚拟机相关的OPCODE
      case None =>
        VM.run(context, blockchainConfig.isDebugTraceEnabled)
    }
  }

  //处理智能合约
  val result = if (stx.tx.isContractCreation && !r.error.isDefined && !r.isRevert) {
    saveCreatedContract(context.env.ownerAddr, r, evmCfg)
  } else {
    r
  }

  if (result.error.isDefined || result.isRevert) {
    // rollback to the world before transfer was done if an error happened
    // the error result may be caused by parallel conflict, so merge all possible modifies
    //合并竞态条件
    result.copy(world = checkpoint.mergeRaceConditions(result.world), addressesToDelete = Set(), addressesTouched = Set(), txLogs = Vector(), parallelRaceConditions = Set(ProgramState.OnError))
  } else {
    result
  }
}
```
</br>
通过上面的反复跳转进入VM：
</br>

```
//首先要处理当前状态，从程序上下文中把状态取出来进行处理
def run[W <: WorldState[W, S], S <: Storage[S]](context: ProgramContext[W, S], isDebugTraceEnabled: Boolean): ProgramResult[W, S] = {
   // new init state is created for each run(context)
   val initState = new ProgramState[W, S](context, isDebugTraceEnabled)
   val postState = run(initState)

   ProgramResult[W, S](
     postState.returnData,
     postState.gas,
     postState.world,
     postState.txLogs,
     postState.gasRefund,
     postState.addressesToDelete,
     postState.addressesTouched,
     postState.error,
     postState.isRevert,
     postState.parallelRaceConditions
   )
 }

 // TODO write debug trace to a file
 @tailrec
 private def run[W <: WorldState[W, S], S <: Storage[S]](state: ProgramState[W, S]): ProgramState[W, S] = {
   val byte = state.program.getByte(state.pc)
   state.config.getOpCode(byte) match {
     case Some(opcode) =>
       if (state.isDebugTraceEnabled) {
         println(s"[trace] $opcode | pc: ${state.pc} | depth: ${state.env.callDepth} | gas: ${state.gas} | ${state.stack} | ${state.memory} | error: ${state.error}")
       }
       //此处开始进行指令级的处理
       val newState = opcode.execute(state) // may reentry VM.run(context) by CREATE/CALL op

       if (newState.isHalted) {
         if (state.isDebugTraceEnabled) {
           println(s"[trace] halt | pc: ${newState.pc} | depth: ${newState.env.callDepth} | gas: ${newState.gas} | ${newState.stack} | ${newState.memory} | error: ${newState.error}")
         }
         newState
       } else {
         run[W, S](newState)
       }

     case None =>
       if (state.isDebugTraceEnabled) {
         println(s"[trace] ${InvalidOpCode(byte)} | pc: ${state.pc} | depth: ${state.env.callDepth} | gas: ${state.gas} | ${state.stack} | error: ${state.error}")
       }
       state.withError(InvalidOpCode(byte)).halt()
   }
 }
```
</br>
他会根据不同的指定来调用不同的处理函数exec,举一个例子在sstore这个指令中，会对世界状态进行存储：
</br>

```
protected def exec[W <: WorldState[W, S], S <: Storage[S]](state: ProgramState[W, S], params: (UInt256, UInt256)): ProgramState[W, S] = {
   if (state.context.isStaticCall) {
     state.withError(StaticCallModification)
   } else {
     val (key, value) = params
     val oldValue = state.storage.load(key)
     val refund = if (value.isZero && oldValue.nonZero) state.config.feeSchedule.R_sclear else 0
     //保存状态
     val updatedStorage = state.storage.store(key, value)
     val world = state.world.saveStorage(state.ownAddress, updatedStorage)

     state
       .withWorld(world)
       .refundGas(refund)
       .step()
   }
 }
```
</br>
其它的都类似，不再一一赘述。
</br>

## 3、并行的再处理
前面提到过，如果状态合并有问题，就会再来一次。看一下这个代码：
</br>

```
def reExecute(stx: SignedTransaction, prevWorld: BlockWorldState) = {
  //保存世界状态和结果
  validateAndExecuteTransaction(stx, blockHeader, stxValidator, evmCfg)(prevWorld.commit().withTx(Some(stx))) match {
  }
}
```
</br>
其实去除相关的处理后发现和第一执行没有啥区别，其实它的原理也就是说，如果第一次合并冲突，那么第二次再执行时，极有可能就已经没有冲突了。
</br>

## 4、并行的验证
</br>

```
override def executeBlock(block: Block, validators: Validators)(implicit executor: ExecutionContext): Future[Either[BlockExecutionError, BlockResult]] = {
  val start1 = System.nanoTime
  ......
  // 根据返回结果来决定是成功还是串行再来一次
  parallelResult flatMap {
    case Right((blockResult, worldCommitted)) => Future.successful(Right(blockResult))

    case left @ Left(error) =>
      log.debug(s"in parallel failed with error $error, try sequential ...")

      val start1 = System.nanoTime
      executeBlockTransactions(block, validators.signedTransactionValidator, isParallel = false) map {
        case Right(blockResult) =>
          log.debug(s"${block.header.number} sequential-executed in ${(System.nanoTime - start1) / 1000000}ms")

          val worldRewardPaid = payBlockReward(block)(blockResult.world)
          val worldCommitted = worldRewardPaid.commit() // State root hash needs to be up-to-date for validateBlockAfterExecution

          validateBlockAfterExecution(block, worldCommitted.stateRootHash, blockResult.receipts, blockResult.gasUsed, validators.blockValidator) match {
            case Right(_)    => Right(blockResult)
            case Left(error) => Left(error)
          }

        case Left(error) => Left(error)
      }
  }
}
```
</br>
验证的代码比较简单，其实就对并行的结果进行一下处理即可。
</br>

## 5、并行的状态合并
状态合并其实是重中之重，前面所有的并行有没有意义，是由他们促成的，如果无法促成，就只能回到串行执行，那成本可就大了。程序会在前面的并行交易函数中调用prevWorld.merge(txResult.world)，看一下这个函数：
</br>

```
//合并竞态条件
def mergeRaceConditions(later: BlockWorldState): BlockWorldState = {
   later.raceConditions foreach {
     case (k, vs) => this.raceConditions += (k -> (this.raceConditions.getOrElse(k, Set()) ++ vs))
   }
   this
 }
//调用此处的合并，它又会对世界状态中的竞态条件，用户trie等进行合并
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
//合并用户的TrieAccount
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
通过上述的一系列的合并，能合并的就合并了不能合并的就返回错误。然后回到串行处理过程。
</br>

## 三、总结
不能不说khipu的并行思路有自己独特的一方面，正如他们的官方的文档上说，处理并行的速度决定于安达尔定理的失败的一方，也有就是说，只有是失败的倒数，从他们自己的官方宣布来看，其提供的数据支持在以太坊公网上应该会有比较明显的提升（并行度可以提高到80%，按照定理，理论上应该有五倍的提升）。
</br>
从khipu总结的经验来看，计算性能的瓶颈有三点：网络广播时延；共识时间长和节点对交易（合约）执行、验证的时间。在时延和共识确定的情况下，提高第三者是一个比较容易达到的目标，但是也是一个比较麻烦的目标。
</br>
从目前来看，包括星云、早期的EOS等都提供了交易并行，各有千秋，各有特色。最新的以太坊也有这个想法，但最终会实现成什么样子，还得拭目以待。
