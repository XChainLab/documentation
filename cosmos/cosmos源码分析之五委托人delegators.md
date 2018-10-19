
# cosmos源码分析之五委托人delegators
## 一、委托人
在整个的cosmos中，委托人是一个非常重要的角色。通过委托机制可以达到全民参与的形式。这在EOS中也有体现。委托人，其实就是本身无力或者不想参与验证过程的人，他们把自己的权益（代币份额）交由某个人来代替执行自己的权益。
</br>
在整个的网络中，验证人的数量是有限的，正如美国大选，总统和议员总是少数，但是他们是由美国公民选举出来的，可以把美国公民理解成委托人。当他们把票投给某个人时，某个人当选，然后当选的人就会有倾向性的做一些工作来回馈投票人。
</br>
在cosmos中，道理是相通的。
</br>

## 二、委托的流程

1、选择验证人
</br>
在委托前，还是要找一个利益最大化的验证人来做为自己的委托者。参照的信息包括：
</br>
验证人的名称、介绍、佣金变化率、最大佣金、最小抵押数量以及初始化佣金比例等。
</br>
2、委托人的说明
</br>
1)委托人应该对验证人进行仔细调查，因为一理验证人有问题，相应的委托人会跟随的被惩罚。
</br>
2)委托人在委托后也要积极监控验证人，保证其合法进行工作，一旦有任何不满意的地方，可以解绑并转身另外一个验证人。
</br>
3)委托人可以通过投票权来制衡他们的验证人。
</br>
3、收益
</br>
在前面提到过为了抵抗通货膨胀，会定期的增发Atom分配给抵押者。这就是一种收益，那么收益有哪些方面呢？
</br>
1)区块增发的Atom奖励。
</br>
2)区块奖励（photon）。比如对硬分叉的投票表决时会有奖励。
</br>
3)交易费用，这个不用细说，几乎所有的链都有这块费用。
</br>
4、佣金
</br>
就如稳健型的投资一样，每个验证人的股权池会根据抵押比例获取收益（利息）。不过，在将这笔收益按比例返给委托人时，验证人有权抽取一笔佣金（手续费），换句话说，委托人想获取收益，就必须向自己委托的验证人提供一笔管理费。
</br>
这里需要说明的是，佣金是委托人给予验证人的。而收益是委托人拿到自己帐户中的。
</br>
5、风险
</br>
把钱给别人用，这个风险是肯定有的。虚拟网络和真实社会没有什么革命性的区别。那么风险体现在哪儿呢？验证人在行使权力的时候儿，Atom是被锁仓的，首先没办法使用，再者，如果验证人犯错误，Atom是要被罚减的。这里面，就包含委托人的代币。什么原因会导致被处罚呢？
</br>
1)重复签名：如果钓鱼者反馈一个验证人在多条链上的相同高度上多次签名，那么就会被惩罚。
</br>
2)不完成工作：也就是说不投票，占着那个不那个。也会被惩罚。
</br>
3)玩失踪：这和2有些类似。
</br>

## 三、源码
</br>
委托人和验证人以及stake相关的部分中会有很强的关系。
</br>
stake.go
</br>
``` go
// delegation bond for a delegated proof of stake system
type Delegation interface {
	GetDelegator() Address // delegator address for the bond
	GetValidator() Address // validator owner address for the bond
	GetBondShares() Rat    // amount of validator's shares
}

// properties for the set of all delegations for a particular
type DelegationSet interface {

	// iterate through all delegations from one delegator by validator-address,
	//   execute func for each validator
	IterateDelegators(Context, delegator Address,
		fn func(index int64, delegation Delegation) (stop bool))
}
```
</br>
委托人的管理封装数据结构。
</br>
delegation.go
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

func (b Delegation) equal(b2 Delegation) bool {
	return bytes.Equal(b.DelegatorAddr, b2.DelegatorAddr) &&
		bytes.Equal(b.ValidatorAddr, b2.ValidatorAddr) &&
		b.Height == b2.Height &&
		b.Shares.Equal(b2.Shares)
}

// ensure fulfills the sdk validator types
var _ sdk.Delegation = Delegation{}

// nolint - for sdk.Delegation
func (b Delegation) GetDelegator() sdk.Address { return b.DelegatorAddr }
func (b Delegation) GetValidator() sdk.Address { return b.ValidatorAddr }
func (b Delegation) GetBondShares() sdk.Rat    { return b.Shares }

//Human Friendly pretty printer
func (b Delegation) HumanReadableString() (string, error) {
	bechAcc, err := sdk.Bech32ifyAcc(b.DelegatorAddr)
	if err != nil {
		return "", err
	}
	bechVal, err := sdk.Bech32ifyAcc(b.ValidatorAddr)
	if err != nil {
		return "", err
	}
	resp := "Delegation \n"
	resp += fmt.Sprintf("Delegator: %s\n", bechAcc)
	resp += fmt.Sprintf("Validator: %s\n", bechVal)
	resp += fmt.Sprintf("Shares: %s", b.Shares.String())
	resp += fmt.Sprintf("Height: %d", b.Height)

	return resp, nil

}
```
</br>
这里需要在处理的handle中控制绑定的委托者和验证人
</br>
handler.go
</br>
``` go
// common functionality between handlers
func delegate(ctx sdk.Context, k Keeper, delegatorAddr sdk.Address,
	bondAmt sdk.Coin, validator Validator) (sdk.Tags, sdk.Error) {

	// Get or create the delegator bond
	bond, found := k.GetDelegation(ctx, delegatorAddr, validator.Owner)
	if !found {
		bond = Delegation{
			DelegatorAddr: delegatorAddr,
			ValidatorAddr: validator.Owner,
			Shares:        sdk.ZeroRat(),
		}
	}

	// Account new shares, save
	pool := k.GetPool(ctx)
	_, _, err := k.coinKeeper.SubtractCoins(ctx, bond.DelegatorAddr, sdk.Coins{bondAmt})
	if err != nil {
		return nil, err
	}
	validator, pool, newShares := validator.addTokensFromDel(pool, bondAmt.Amount)
	bond.Shares = bond.Shares.Add(newShares)

	// Update bond height
	bond.Height = ctx.BlockHeight()

	k.setPool(ctx, pool)
	k.setDelegation(ctx, bond)
	k.updateValidator(ctx, validator)
	tags := sdk.NewTags("action", []byte("delegate"), "delegator", delegatorAddr.Bytes(), "validator", validator.Owner.Bytes())
	return tags, nil
}
```
</br>

将委托者和验证人绑定在一起是通过Msg的bond和unbond来实现的。
</br>

msg.go:
</br>

``` go
// MsgDelegate - struct for bonding transactions
type MsgDelegate struct {
	DelegatorAddr sdk.Address `json:"delegator_addr"`
	ValidatorAddr sdk.Address `json:"validator_addr"`
	Bond          sdk.Coin    `json:"bond"`
}

func NewMsgDelegate(delegatorAddr, validatorAddr sdk.Address, bond sdk.Coin) MsgDelegate {
	return MsgDelegate{
		DelegatorAddr: delegatorAddr,
		ValidatorAddr: validatorAddr,
		Bond:          bond,
	}
}

// MsgUnbond - struct for unbonding transactions
type MsgUnbond struct {
	DelegatorAddr sdk.Address `json:"delegator_addr"`
	ValidatorAddr sdk.Address `json:"validator_addr"`
	Shares        string      `json:"shares"`
}

func NewMsgUnbond(delegatorAddr, validatorAddr sdk.Address, shares string) MsgUnbond {
	return MsgUnbond{
		DelegatorAddr: delegatorAddr,
		ValidatorAddr: validatorAddr,
		Shares:        shares,
	}
}
```
</br>

# 四、总结

通过上面的分析和说明，可以看出，委托人其实就是普通的网络节点，验证人的资格也不是你想有就有的。POS的机制决定了跟和资本主义社会一样，没有足够的金钱，没法参加大选。
</br>
这也是POS饱受诟病的地方，在COSMOS中也有一些防止的方法，但目前看来还不能从根本上解决问题。所以委托人在委托时，还是不要任性。
</br>

