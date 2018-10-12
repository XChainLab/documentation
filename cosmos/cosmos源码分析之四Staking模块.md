# cosmos源码分析之四Staking模块

## 一、术语
在前面的分析中提到了Cosmos有几个重要的机制，其中一个就是Staking。在分析这个模块之前，需要把一些相关的术语说明一下：
</br>
Atom ：Cosmsos原生权益代币（另外有一个费用代币Photon）。
</br>
Atom holder：Atom代币所有者。
</br>
Candidate：Validator的候选人，全节点的Atom代币所有者。
</br>
Validator（验证人）：由Candidate选举出来，负责对 Tendermint 共识中的消息进行签名。
</br>
Delegator（ 代理人）：把自己的Atom代币交由其它Validator（或Candidate）的持有并拥有其权益。
</br>
Bonding Atoms（绑定Atom）：Atom锁定机制（使Atom受共识协议的控制），Atoms只能通过Validator或Candidate进行绑定，如果Validator作恶，那么他绑定的Atom就会受到损失。如果在一个解绑时限内没有被惩罚，Atom持有者就可以重获对他绑定的Atom的支配权。
</br>
Unbonding period（解绑时限）：从解绑操作到Atom持有者重获对这些Atom支配权的缓冲时间。
</br>
Inflationary provisions（通货膨胀）：Cosmos Hub周期性的创建Atom，并根据规则分发给绑定Atom的持有者，用于鼓励Atom的有者尽可能多的绑定他们的Atom代币。
</br>
Transaction fees（交易费）：指包含在一个Cosmos Hub的交易中的手续费，由Validator取得，并根据Validator和Delegator绑定的Atom数量进行分配。
</br>
Commission fee （佣金）：Validator为他所提供的服务从交易费中收取佣金。
</br>

## 二、源码
</br>
stake的源码在x/stake中，代码老大一片，稳住。
</br>

``` golang
// Pool - dynamic parameters of the current state
type Pool struct {
	LooseUnbondedTokens int64   `json:"loose_unbonded_tokens"` // tokens not associated with any validator
	UnbondedTokens      int64   `json:"unbonded_tokens"`       // reserve of unbonded tokens held with validators
	UnbondingTokens     int64   `json:"unbonding_tokens"`      // tokens moving from bonded to unbonded pool
	BondedTokens        int64   `json:"bonded_tokens"`         // reserve of bonded tokens
	UnbondedShares      sdk.Rat `json:"unbonded_shares"`       // sum of all shares distributed for the Unbonded Pool
	UnbondingShares     sdk.Rat `json:"unbonding_shares"`      // shares moving from Bonded to Unbonded Pool
	BondedShares        sdk.Rat `json:"bonded_shares"`         // sum of all shares distributed for the Bonded Pool
	InflationLastTime   int64   `json:"inflation_last_time"`   // block which the last inflation was processed // TODO make time
	Inflation           sdk.Rat `json:"inflation"`             // current annual inflation rate

	DateLastCommissionReset int64 `json:"date_last_commission_reset"` // unix timestamp for last commission accounting reset (daily)

	// Fee Related
	PrevBondedShares sdk.Rat `json:"prev_bonded_shares"` // last recorded bonded shares - for fee calcualtions
}
type PoolShares struct {
	Status sdk.BondStatus `json:"status"`
	Amount sdk.Rat        `json:"amount"` // total shares of type ShareKind
}

// Validator defines the total amount of bond shares and their exchange rate to
// coins. Accumulation of interest is modelled as an in increase in the
// exchange rate, and slashing as a decrease.  When coins are delegated to this
// validator, the validator is credited with a Delegation whose number of
// bond shares is based on the amount of coins delegated divided by the current
// exchange rate. Voting power can be calculated as total bonds multiplied by
// exchange rate.
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

// keeper of the staking store
type Keeper struct {
	storeKey   sdk.StoreKey
	cdc        *wire.Codec
	coinKeeper bank.Keeper

	// codespace
	codespace sdk.CodespaceType
}
```
</br>
上面列举了几个关键的数据结构，特别是最后一个，在前面分析时提到过，Keeper实际上是数据库上层抽象的一个数据结构体。在Cosmos中，Pool是整个全局状态的管理空间。它能够跟踪所有帐户持有的Atomic的状态，包括移动和通化膨胀信息等。
</br>
也就是说它是一个Atom的集合，在Cosmos中有两个全局的pool，绑定池和解绑池。需要说明的是，这个Pool是一个逻辑上的概念，Share是Atom分配的一个单位，通过一些计算公式可以得到Atom，这个有一点类似于以太坊的Gas。但用途有些不同。当然，它的好处在于，可以用于非侵入式的修改相关者的Atom的数量，类似于一个动态的汇率管制机制。
</br>

``` go
// equivalent amount of shares if the shares were bonded
func (s PoolShares) ToBonded(p Pool) PoolShares {
	var amount sdk.Rat
	switch s.Status {
	case sdk.Bonded:
		amount = s.Amount
	case sdk.Unbonding:
		exRate := p.unbondingShareExRate().Quo(p.bondedShareExRate()) // (tok/ubshr)/(tok/bshr) = bshr/ubshr
		amount = s.Amount.Mul(exRate)                                 // ubshr*bshr/ubshr = bshr
	case sdk.Unbonded:
		exRate := p.unbondedShareExRate().Quo(p.bondedShareExRate()) // (tok/ubshr)/(tok/bshr) = bshr/ubshr
		amount = s.Amount.Mul(exRate)                                // ubshr*bshr/ubshr = bshr
	}
	return NewUnbondedShares(amount)
}

//_________________________________________________________________________________________________________

// get the equivalent amount of tokens contained by the shares
func (s PoolShares) Tokens(p Pool) sdk.Rat {
	switch s.Status {
	case sdk.Bonded:
		return p.unbondedShareExRate().Mul(s.Amount) // (tokens/shares) * shares
	case sdk.Unbonding:
		return p.unbondedShareExRate().Mul(s.Amount)
	case sdk.Unbonded:
		return p.unbondedShareExRate().Mul(s.Amount)
	default:
		panic("unknown share kind")
	}
}
```
</br>
对于代理人同样也适用这个算法来进行Atom的管理。
</br>

``` go
// Delegation represents the bond with tokens held by an account.  It is
// owned by one delegator, and is associated with the voting power of one
// pubKey.
// TODO better way of managing space
type Delegation struct {
	DelegatorAddr sdk.Address `json:"delegator_addr"`
	ValidatorAddr sdk.Address `json:"validator_addr"`
	Shares        sdk.Rat     `json:"shares"`
	Height        int64       `json:"height"` // Last height bond updated
}
```
</br>
通货膨胀也是Cosmos一个机制：
</br>

``` go
var hrsPerYrRat = sdk.NewRat(hrsPerYr) // as defined by a julian year of 365.25 days

// process provisions for an hour period
func (k Keeper) processProvisions(ctx sdk.Context) Pool {

	pool := k.GetPool(ctx)
	pool.Inflation = k.nextInflation(ctx)

	// Because the validators hold a relative bonded share (`GlobalStakeShare`), when
	// more bonded tokens are added proportionally to all validators the only term
	// which needs to be updated is the `BondedPool`. So for each previsions cycle:

	provisions := pool.Inflation.Mul(sdk.NewRat(pool.TokenSupply())).Quo(hrsPerYrRat).Evaluate()
	pool.BondedTokens += provisions
	return pool
}

// get the next inflation rate for the hour
func (k Keeper) nextInflation(ctx sdk.Context) (inflation sdk.Rat) {

	params := k.GetParams(ctx)
	pool := k.GetPool(ctx)
	// The target annual inflation rate is recalculated for each previsions cycle. The
	// inflation is also subject to a rate change (positive of negative) depending or
	// the distance from the desired ratio (67%). The maximum rate change possible is
	// defined to be 13% per year, however the annual inflation is capped as between
	// 7% and 20%.

	// (1 - bondedRatio/GoalBonded) * InflationRateChange
	inflationRateChangePerYear := sdk.OneRat().Sub(pool.bondedRatio().Quo(params.GoalBonded)).Mul(params.InflationRateChange)
	inflationRateChange := inflationRateChangePerYear.Quo(hrsPerYrRat)

	// increase the new annual inflation for this next cycle
	inflation = pool.Inflation.Add(inflationRateChange)
	if inflation.GT(params.InflationMax) {
		inflation = params.InflationMax
	}
	if inflation.LT(params.InflationMin) {
		inflation = params.InflationMin
	}

	return inflation.Round(precision)
}

```
</br>
它还是比较好理解的，增加一个系数来处理。
</br>

## 三、总结
</br>
Staking模块是主要的资金管理模块，具体的技术问题没有什么，主要还是一些规则的制定，明白了这些规则，在理解分析Cosmos时会省不少的时间。
</br>
