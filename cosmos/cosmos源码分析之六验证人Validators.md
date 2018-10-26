# cosmos源码分析之六验证人
##  一、简介
在整个cosmos中，验证人的角色是非常重要的，它们负责投票决定向区块链提交新的区块。或者可以理解成，没有验证人，就没有cosmos的区块，也就没有区块链之说。
</br>
验证人可以由普通用户通过质押Atom来成为验证人，当然也可以接受别人的委托，这在上文已经分析过了，验证人由其总股权来决定即质押股权最多的前一百人会成为Cosmos的验证人。在Cosmos网络中，验证人的上限是一百，然后每年增长约在百分之十三，最终稳定在三百人左右。
</br>
如果验证人胡作非为或者经常不在线，又或者没有参与到治理，那么他的相关的抵押的Atom会被Slash掉。Slash的数量根据具体的情况来决定。
</br>
做为验证人，对硬件的要求有一定的限制，其实这和EOS的超级节点有些类似，毕竟做为一个验证人节点，没事就下线，被罚钱也不是什么好事，所以还是需要有一定的环境基础做保证。做为什么一个验证人的要求的细节，大家可以去官网查找相关的资料，这玩意目前还不能算多靠谱。
</br>

##  二、相关的术语
</br>
1、验证人：Cosmos Hub基于Tendermint，它由一组（100~300）个验证人来保证网络的安全。验证人负责去运行一个全节点，广播经过验证人私钥签名过的加密信息来参与共识。验证人最终根据投票的结果来决定新的区块并因此得到奖励。
</br>
2、股权抵押：Cosmos Hub是一个POS的区块链，意味着验证人的权重由其提供质押的Atom的数量决定。形象的来说，谁抵押的钱多，入的股多，权力就越大，大到在top100时，就成了验证人。
</br>
3、全节点：全节点就是能够完成区块链的所有功能的节点。相对应的还有轻节点，它处理区块头和小部分的交易。
</br>

## 三、成为验证人的过程
</br>
网络中的节点均可以发送一笔"declare-candidacy"交易用来表示他们想成为一个验证人，同时必须填写以下参数：
验证人公钥、名称、验证人的网站（可选）、验证人的描述信息（可选）、初始佣金比例、最大佣金、佣金变化率、最小自抵押数量、初始自抵押数量。
如果某个节点参选，其它Atom持有者可以向其地址委托Atom，从而有效地向其股权池里增加股权。一个地址的所有股权是其自抵押的Atom和委托人委托的股权的总和。
Top100的候选者被任命为验证人。如果某个验证人的股权总量跌出了前100名就会失去验证人权利，验证人的最大数量会依照计时按时间逐渐增加：
从第一年到最后一年的分布为100，113，127，144，163，184，208，235，265，300.
</br>

## 四、源码分析
在x/stake的目录中，有验证人的源码（x/stake/validator.go）：
</br>

``` golang
type Validator struct {
	Owner   sdk.Address   `json:"owner"`   // sender of BondTx - UnbondTx returns here
	PubKey  crypto.PubKey `json:"pub_key"` // pubkey of validator
	Revoked bool          `json:"revoked"` // has the validator been revoked from bonded status?

	PoolShares      PoolShares `json:"pool_shares"`      // total shares for tokens held in the pool
	DelegatorShares sdk.Rat    `json:"delegator_shares"` // total shares issued to a validator's delegators

	Description        Description `json:"description"`           // description terms for the validator
	BondHeight         int64       `json:"bond_height"`           // earliest height as a bonded validator
	BondIntraTxCounter int16       `json:"bond_intra_tx_counter"` // block-local tx index of validator change
	ProposerRewardPool sdk.Coins   `json:"proposer_reward_pool"`  // XXX reward pool collected from being the proposer

	Commission            sdk.Rat `json:"commission"`              // XXX the commission rate of fees charged to any delegators
	CommissionMax         sdk.Rat `json:"commission_max"`          // XXX maximum commission rate which this validator can ever charge
	CommissionChangeRate  sdk.Rat `json:"commission_change_rate"`  // XXX maximum daily increase of the validator commission
	CommissionChangeToday sdk.Rat `json:"commission_change_today"` // XXX commission rate change today, reset each day (UTC time)

	// fee related
	PrevBondedShares sdk.Rat `json:"prev_bonded_shares"` // total shares of a global hold pools
}

// Validators - list of Validators
type Validators []Validator

//委托人增加委托
// XXX Audit this function further to make sure it's correct
// add tokens to a validator
func (v Validator) addTokensFromDel(pool Pool,
	amount int64) (validator2 Validator, p2 Pool, issuedDelegatorShares sdk.Rat) {

	exRate := v.DelegatorShareExRate(pool) // bshr/delshr

	var poolShares PoolShares
	var equivalentBondedShares sdk.Rat
	switch v.Status() {
	case sdk.Unbonded:
		pool, poolShares = pool.addTokensUnbonded(amount)
	case sdk.Unbonding:
		pool, poolShares = pool.addTokensUnbonding(amount)
	case sdk.Bonded:
		pool, poolShares = pool.addTokensBonded(amount)
	}
	v.PoolShares.Amount = v.PoolShares.Amount.Add(poolShares.Amount)
	equivalentBondedShares = poolShares.ToBonded(pool).Amount

	issuedDelegatorShares = equivalentBondedShares.Quo(exRate) // bshr/(bshr/delshr) = delshr
	v.DelegatorShares = v.DelegatorShares.Add(issuedDelegatorShares)

	return v, pool, issuedDelegatorShares
}

//stake.go
// validator for a delegated proof of stake system
//相关的验证人的接口函数，在上述的验证人结构中有体现
type Validator interface {
	GetStatus() BondStatus    // status of the validator
	GetOwner() Address        // owner address to receive/return validators coins
	GetPubKey() crypto.PubKey // validation pubkey
	GetPower() Rat            // validation power
	GetBondHeight() int64     // height in which the validator became active
}
// properties for the set of all validators
type ValidatorSet interface {
	// iterate through validator by owner-address, execute func for each validator
	IterateValidators(Context,
		func(index int64, validator Validator) (stop bool))

	// iterate through bonded validator by pubkey-address, execute func for each validator
	IterateValidatorsBonded(Context,
		func(index int64, validator Validator) (stop bool))

	Validator(Context, Address) Validator     // get a particular validator by owner address
	TotalPower(Context) Rat                   // total power of the validator set
	Slash(Context, crypto.PubKey, int64, Rat) // slash the validator and delegators of the validator, specifying offence height & slash fraction
	Revoke(Context, crypto.PubKey)            // revoke a validator
	Unrevoke(Context, crypto.PubKey)          // unrevoke a validator
}
```
</br>
创建验证人命令的源码：
</br>

``` golang
// create create validator command
func GetCmdCreateValidator(cdc *wire.Codec) *cobra.Command {
	cmd := &cobra.Command{
		Use:   "create-validator",
		Short: "create new validator initialized with a self-delegation to it",
		RunE: func(cmd *cobra.Command, args []string) error {
			ctx := context.NewCoreContextFromViper().WithDecoder(authcmd.GetAccountDecoder(cdc))

			amount, err := sdk.ParseCoin(viper.GetString(FlagAmount))
			if err != nil {
				return err
			}
			validatorAddr, err := sdk.GetAccAddressBech32(viper.GetString(FlagAddressValidator))
			if err != nil {
				return err
			}

			pkStr := viper.GetString(FlagPubKey)
			if len(pkStr) == 0 {
				return fmt.Errorf("must use --pubkey flag")
			}
			pk, err := sdk.GetValPubKeyBech32(pkStr)
			if err != nil {
				return err
			}
			if viper.GetString(FlagMoniker) == "" {
				return fmt.Errorf("please enter a moniker for the validator using --moniker")
			}
			description := stake.Description{
				Moniker:  viper.GetString(FlagMoniker),
				Identity: viper.GetString(FlagIdentity),
				Website:  viper.GetString(FlagWebsite),
				Details:  viper.GetString(FlagDetails),
			}
			msg := stake.NewMsgCreateValidator(validatorAddr, pk, amount, description)

			// build and sign the transaction, then broadcast to Tendermint
			res, err := ctx.EnsureSignBuildBroadcast(ctx.FromAddressName, msg, cdc)
			if err != nil {
				return err
			}

			fmt.Printf("Committed at block %d. Hash: %s\n", res.Height, res.Hash.String())
			return nil
		},
	}

	cmd.Flags().AddFlagSet(fsPk)
	cmd.Flags().AddFlagSet(fsAmount)
	cmd.Flags().AddFlagSet(fsDescription)
	cmd.Flags().AddFlagSet(fsValidator)
	return cmd
}
```
</br>
在Cosmos-SDK中，主要是提供了一些数据结构及相关的操作的验证人过程，而在Tendermint中则是提供了数据的具体的流动和通信接口。而在ABCI中提供了开发应用程序的接口和相关的协议。它是区块链和Tendermint的接口。只有通过它才可以接入相关的应用程序。
</br>
这里提到了，在Tendermint中也包含有相关的验证人的部分：
</br>
//types/validator.go

``` golang
// Volatile state for each Validator
// NOTE: The Accum is not included in Validator.Hash();
// make sure to update that method if changes are made here
type Validator struct {
	Address     Address       `json:"address"`
	PubKey      crypto.PubKey `json:"pub_key"`
	VotingPower int64         `json:"voting_power"`

	Accum int64 `json:"accum"`
}

// RandValidator returns a randomized validator, useful for testing.
// UNSTABLE
func RandValidator(randPower bool, minPower int64) (*Validator, PrivValidator) {
	privVal := NewMockPV()
	votePower := minPower
	if randPower {
		votePower += int64(cmn.RandUint32())
	}
	val := NewValidator(privVal.GetPubKey(), votePower)
	return val, privVal
}


```
</br>

//state/validation.go
</br>
它有一个重要的工作-验证块：
</br>

``` golang
// Validate block
//验证块
func validateBlock(stateDB dbm.DB, s State, b *types.Block) error {
	// validate internal consistency
	if err := b.ValidateBasic(); err != nil {
		return err
	}

	// validate basic info
	if b.ChainID != s.ChainID {
		return fmt.Errorf("Wrong Block.Header.ChainID. Expected %v, got %v", s.ChainID, b.ChainID)
	}
	if b.Height != s.LastBlockHeight+1 {
		return fmt.Errorf("Wrong Block.Header.Height. Expected %v, got %v", s.LastBlockHeight+1, b.Height)
	}
	/*	TODO: Determine bounds for Time
		See blockchain/reactor "stopSyncingDurationMinutes"

		if !b.Time.After(lastBlockTime) {
			return errors.New("Invalid Block.Header.Time")
		}
	*/

	// validate prev block info
	if !b.LastBlockID.Equals(s.LastBlockID) {
		return fmt.Errorf("Wrong Block.Header.LastBlockID.  Expected %v, got %v", s.LastBlockID, b.LastBlockID)
	}
	newTxs := int64(len(b.Data.Txs))
	if b.TotalTxs != s.LastBlockTotalTx+newTxs {
		return fmt.Errorf("Wrong Block.Header.TotalTxs. Expected %v, got %v", s.LastBlockTotalTx+newTxs, b.TotalTxs)
	}

	// validate app info
	if !bytes.Equal(b.AppHash, s.AppHash) {
		return fmt.Errorf("Wrong Block.Header.AppHash.  Expected %X, got %v", s.AppHash, b.AppHash)
	}
	if !bytes.Equal(b.ConsensusHash, s.ConsensusParams.Hash()) {
		return fmt.Errorf("Wrong Block.Header.ConsensusHash.  Expected %X, got %v", s.ConsensusParams.Hash(), b.ConsensusHash)
	}
	if !bytes.Equal(b.LastResultsHash, s.LastResultsHash) {
		return fmt.Errorf("Wrong Block.Header.LastResultsHash.  Expected %X, got %v", s.LastResultsHash, b.LastResultsHash)
	}
	if !bytes.Equal(b.ValidatorsHash, s.Validators.Hash()) {
		return fmt.Errorf("Wrong Block.Header.ValidatorsHash.  Expected %X, got %v", s.Validators.Hash(), b.ValidatorsHash)
	}

	// Validate block LastCommit.
	if b.Height == 1 {
		if len(b.LastCommit.Precommits) != 0 {
			return errors.New("Block at height 1 (first block) should have no LastCommit precommits")
		}
	} else {
		if len(b.LastCommit.Precommits) != s.LastValidators.Size() {
			return fmt.Errorf("Invalid block commit size. Expected %v, got %v",
				s.LastValidators.Size(), len(b.LastCommit.Precommits))
		}
		err := s.LastValidators.VerifyCommit(
			s.ChainID, s.LastBlockID, b.Height-1, b.LastCommit)
		if err != nil {
			return err
		}
	}

	// TODO: Each check requires loading an old validator set.
	// We should cap the amount of evidence per block
	// to prevent potential proposer DoS.
	for _, ev := range b.Evidence.Evidence {
		if err := VerifyEvidence(stateDB, s, ev); err != nil {
			return types.NewEvidenceInvalidErr(ev, err)
		}
	}

	return nil
}
```
</br>
在ABCI的相关软件中也定义了Validator这个数据结构：
</br>

``` golang
// Validator
type Validator struct {
	Address []byte `protobuf:"bytes,1,opt,name=address,proto3" json:"address,omitempty"`
	PubKey  PubKey `protobuf:"bytes,2,opt,name=pub_key,json=pubKey" json:"pub_key"`
	Power   int64  `protobuf:"varint,3,opt,name=power,proto3" json:"power,omitempty"`
}

```
</br>
然后再看一个出块时调用的相关操作，它先是进行判断异常特别是双签，然后遍历验证人来对块进行签名。
</br>

``` golang
// slashing begin block functionality
func BeginBlocker(ctx sdk.Context, req abci.RequestBeginBlock, sk Keeper) (tags sdk.Tags) {
	// Tag the height
	heightBytes := make([]byte, 8)
	binary.LittleEndian.PutUint64(heightBytes, uint64(req.Header.Height))
	tags = sdk.NewTags("height", heightBytes)

	// Deal with any equivocation evidence
	for _, evidence := range req.ByzantineValidators {
		pk, err := tmtypes.PB2TM.PubKey(evidence.Validator.PubKey)
		if err != nil {
			panic(err)
		}
		switch string(evidence.Type) {
		case tmtypes.ABCIEvidenceTypeDuplicateVote:
			sk.handleDoubleSign(ctx, evidence.Height, evidence.Time, pk)
		default:
			ctx.Logger().With("module", "x/slashing").Error(fmt.Sprintf("Ignored unknown evidence type: %s", string(evidence.Type)))
		}
	}

	// Iterate over all the validators  which *should* have signed this block
	for _, validator := range req.Validators {
		present := validator.SignedLastBlock
		pubkey, err := tmtypes.PB2TM.PubKey(validator.Validator.PubKey)
		if err != nil {
			panic(err)
		}
		sk.handleValidatorSignature(ctx, pubkey, present)
	}

	return
}
```
</br>
通过这些接口不断的定义相关的验证人的数据结构，在不同的状态下进行转换，来达到验证人在不同阶段的状态的控制，更详细的代码，因为项目未最终完成，不进一步的阐述。其中的细节还有很多，相关验证人部分的代码也在演进中。

</br>
</br>
