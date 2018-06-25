# eos源码分析之六共识

## 一、EOS使用的共识
EOS使用的是与传统的共识方法不同的DPOS共识机制，而且在最新的版本中已经更改为了BFT-DPOS机制，在网上看到BM说他又找到了一种更新的共识机制，可以解决被超级节点控制的问题，不知道最终会是什么样子，在比特币和以太坊都使用POW的共识的前提下，EOS使用DPOS机制，可以说是解决高并发的一个比较好的方法。但是，DPOS机制很容易由于节点太少被攻击，事实上也是如此。那么什么是DPOS呢？EOS是怎么使用其进行块之间的共识的呢？
 </br>
 提到dpos,就不得不提到pos,PoS全称Proof of Stake，意为权益证明。说得直白一些就是谁存款多，存款时间长，谁就有权出块（记帐）。这个解决了POW一个痛点，即它不用挖矿，所以也不用耗费老多的电能。但是这这个算法有个致命问题，资本决定了一切，所以很容易被有钱人垄断。
 </br>
 DPOS比POS多了一个D，它的意义是授权，委托。二者的区别是，DPOS需要POS的持有者来通过选举代表，由代表实现出块。而在EOS中则有21个出块者（BP,BlcokProducer），或者叫超级节点。还有101个备份节点。当21个BP的15个确认交易后，交易即不可逆转。
 </br>

## 二、共识的过程  
 </br>
 1、初始化的共识
 </br>
 EOS初始启动是外在选举的21个超级节点，所以不涉及代码部分。但是一旦启动后会开始新的节点选举，选举成功后，将进行BFT-DPOS共识。
 </br>
 2、选举
 </br>
 主要的代码在contracts/social和eosio.system/voting.cpp中。在cleos的main.cpp中会发现几个数据结构体和相关的应用：
 </br>

 ``` c++

 auto registerProducer = register_producer_subcommand(system);
 auto unregisterProducer = unregister_producer_subcommand(system);

 auto voteProducer = system->add_subcommand("voteproducer", localized("Vote for a producer"));
 voteProducer->require_subcommand();
 auto voteProxy = vote_producer_proxy_subcommand(voteProducer);
 auto voteProducers = vote_producers_subcommand(voteProducer);
 auto approveProducer = approve_producer_subcommand(voteProducer);
 auto unapproveProducer = unapprove_producer_subcommand(voteProducer);

 auto listProducers = list_producers_subcommand(system);

 auto delegateBandWidth = delegate_bandwidth_subcommand(system);
 auto undelegateBandWidth = undelegate_bandwidth_subcommand(system);
 auto listBandWidth = list_bw_subcommand(system);
 ```
 </br>
 这些代码会驱动程序在启动后进行相应的动作。选举在EOS中其实也分成两类，即每人独自发起选举，也可以通过代理人代替自己选举，但结果就是本人就无法再投票了。相应的代码如下：
 </br>

 ``` c++
 /**
 *  @pre producers must be sorted from lowest to highest and must be registered and active
 *  @pre if proxy is set then no producers can be voted for
 *  @pre if proxy is set then proxy account must exist and be registered as a proxy
 *  @pre every listed producer or proxy must have been previously registered
 *  @pre voter must authorize this action
 *  @pre voter must have previously staked some EOS for voting
 *  @pre voter->staked must be up to date
 *
 *  @post every producer previously voted for will have vote reduced by previous vote weight
 *  @post every producer newly voted for will have vote increased by new vote amount
 *  @post prior proxy will proxied_vote_weight decremented by previous vote weight
 *  @post new proxy will proxied_vote_weight incremented by new vote weight
 *
 *  If voting for a proxy, the producer votes will not change until the proxy updates their own vote.
 */
 //上面的介绍过程挺详细
 void system_contract::voteproducer( const account_name voter_name, const account_name proxy, const std::vector<account_name>& producers ) {
    require_auth( voter_name );//验证资格
    update_votes( voter_name, proxy, producers, true );
 }
 void system_contract::update_votes( const account_name voter_name, const account_name proxy, const std::vector<account_name>& producers, bool voting ) {
   //validate input
   if ( proxy ) {//判断是否为代理
      eosio_assert( producers.size() == 0, "cannot vote for producers and proxy at same time" );
      eosio_assert( voter_name != proxy, "cannot proxy to self" );
      require_recipient( proxy );//添加代理帐户
   } else {
      eosio_assert( producers.size() <= 30, "attempt to vote for too many producers" );
      for( size_t i = 1; i < producers.size(); ++i ) { //验证英文注释中的排序
         eosio_assert( producers[i-1] < producers[i], "producer votes must be unique and sorted" );
      }
   }

   //验证资格
   auto voter = \_voters.find(voter_name);
   eosio_assert( voter \!= \_voters.end(), "user must stake before they can vote" ); /// staking creates voter object
   eosio_assert( !proxy || !voter->is_proxy, "account registered as a proxy is not allowed to use a proxy" );

   /*
    * The first time someone votes we calculate and set last_vote_weight, since they cannot unstake until
    * after total_activated_stake hits threshold, we can use last_vote_weight to determine that this is
    * their first vote and should consider their stake activated.
    \*/
  //计算权重，用来控制其抵押股权状态，并确定其是否为第一次投票
   if( voter->last_vote_weight <= 0.0 ) {
    \_gstate.total_activated_stake += voter->staked;
      if( \_gstate.total_activated_stake >= min_activated_stake ) {
         \_gstate.thresh_activated_stake_time = current_time();
      }
   }

   //计算权重
   auto new_vote_weight = stake2vote( voter->staked );
   if( voter->is_proxy ) {//是否代理
      new_vote_weight += voter->proxied_vote_weight;
   }

  //处理投票
   boost::container::flat_map<account_name, pair<double, bool /*new*/> > producer_deltas;
   if ( voter->last_vote_weight > 0 ) {
      if( voter->proxy ) {
         auto old_proxy = \_voters.find( voter->proxy );
         eosio_assert( old_proxy != \_voters.end(), "old proxy not found" ); //data corruption
         \_voters.modify( old_proxy, 0, [&]( auto& vp ) {//投票后减去相应权重，对应英文注释
               vp.proxied_vote_weight -= voter->last_vote_weight;
            });
         propagate_weight_change( *old_proxy ); //继续更新相关权重
      } else {
        //非代理直接操作，一票三十投
         for( const auto& p : voter->producers ) {
            auto& d = producer_deltas[p];
            d.first -= voter->last_vote_weight;
            d.second = false;
         }
      }
   }

   //处理得票
   if( proxy ) {//处理代理
      auto new_proxy = \_voters.find( proxy );
      eosio_assert( new_proxy != \_voters.end(), "invalid proxy specified" ); //if ( !voting ) { data corruption } else { wrong vote }
      eosio_assert( !voting || new_proxy->is_proxy, "proxy not found" );
      if ( new_vote_weight >= 0 ) {
         \_voters.modify( new_proxy, 0, [&]( auto& vp ) {
               vp.proxied_vote_weight += new_vote_weight;
            });
         propagate_weight_change( *new_proxy );
      }
   } else {
      if( new_vote_weight >= 0 ) {
         for( const auto& p : producers ) {
            auto& d = producer_deltas[p];
            d.first += new_vote_weight;
            d.second = true;
         }
      }
   }

  //  投票资格验证
   for( const auto& pd : producer_deltas ) {
      auto pitr = \_producers.find( pd.first );
      if( pitr != \_producers.end() ) {
         eosio_assert( !voting || pitr->active() || !pd.second.second /* not from new set */, "producer is not currently registered" );
         \_producers.modify( pitr, 0, [&]( auto& p ) {
            p.total_votes += pd.second.first;
            if ( p.total_votes < 0 ) { // floating point arithmetics can give small negative numbers
               p.total_votes = 0;
            }
            \_gstate.total_producer_vote_weight += pd.second.first;
            //eosio_assert( p.total_votes >= 0, "something bad happened" );
         });
      } else {
         eosio_assert( !pd.second.second /* not from new set */, "producer is not registered" ); //data corruption
      }
   }

  //更新选举状态
   \_voters.modify( voter, 0, [&]( auto& av ) {
      av.last_vote_weight = new_vote_weight;
      av.producers = producers;
      av.proxy     = proxy;
   });
}
 ```
 </br>
 在前面的投票过程中发现，其实要想选举和成为出块者，都需要先行去注册，在最初的Main函数里也提到相应的子命令，那么看一下对应的代码：
 </br>

 ``` c++
 /**
  *  This method will create a producer_config and producer_info object for 'producer'
  *
  *  @pre producer is not already registered
  *  @pre producer to register is an account
  *  @pre authority of producer to register
  *
  */
 void system_contract::regproducer( const account_name producer, const eosio::public_key& producer_key, const std::string& url, uint16_t location ) {
    eosio_assert( url.size() < 512, "url too long" );
    eosio_assert( producer_key != eosio::public_key(), "public key should not be the default value" );
    require_auth( producer );

    //查找是否已注册
    auto prod = \_producers.find( producer );

    if ( prod != \_producers.end() ) { //已注册
       if( producer_key != prod->producer_key ) {//已注册，但KEY不同，即同名不同人，修改相关设置
           \_producers.modify( prod, producer, [&]( producer_info& info ){
                info.producer_key = producer_key;
                info.is_active    = true;
                info.url          = url;
                info.location     = location;
           });
       }
    } else {//全新加入
       \_producers.emplace( producer, [&]( producer_info& info ){
             info.owner         = producer;
             info.total_votes   = 0;
             info.producer_key  = producer_key;
             info.is_active     = true;
             info.url           = url;
             info.location      = location;
       });
    }
 }
//找到相关，删除
 void system_contract::unregprod( const account_name producer ) {
    require_auth( producer );

    const auto& prod = \_producers.get( producer, "producer not found" );

    \_producers.modify( prod, 0, [&]( producer_info& info ){
          info.deactivate();
    });
 }
//更新相关出块人
 void system_contract::update_elected_producers( block_timestamp block_time ) {
    \_gstate.last_producer_schedule_update = block_time;

    auto idx = \_producers.get_index<N(prototalvote)>();

    std::vector< std::pair<eosio::producer_key,uint16_t> > top_producers;
    top_producers.reserve(21);//一票30投，但只取21，后49备用，再后忽略

    for ( auto it = idx.cbegin(); it != idx.cend() && top_producers.size() < 21 && 0 < it->total_votes && it->active(); ++it ) {
       top_producers.emplace_back( std::pair<eosio::producer_key,uint16_t>({{it->owner, it->producer_key}, it->location}) );
    }

    if ( top_producers.size() < \_gstate.last_producer_schedule_size ) {
       return;
    }

    /// sort by producer name
    std::sort( top_producers.begin(), top_producers.end() );

    std::vector<eosio::producer_key> producers;

    producers.reserve(top_producers.size());
    for( const auto& item : top_producers )
       producers.push_back(item.first);

    bytes packed_schedule = pack(producers);

    if( set_proposed_producers( packed_schedule.data(),  packed_schedule.size() ) >= 0 ) {
       \_gstate.last_producer_schedule_size = static_cast<decltype(\_gstate.last_producer_schedule_size)>( top_producers.size() );
    }
 }
 /**
 *  An account marked as a proxy can vote with the weight of other accounts which
 *  have selected it as a proxy. Other accounts must refresh their voteproducer to
 *  update the proxy's weight.
 *
 *  @param isproxy - true if proxy wishes to vote on behalf of others, false otherwise
 *  @pre proxy must have something staked (existing row in voters table)
 *  @pre new state must be different than current state
 */
 //注册成代理人
void system_contract::regproxy( const account_name proxy, bool isproxy ) {
   require_auth( proxy );

   auto pitr = \_voters.find(proxy);
   if ( pitr != \_voters.end() ) {
      eosio_assert( isproxy != pitr->is_proxy, "action has no effect" );
      eosio_assert( !isproxy || !pitr->proxy, "account that uses a proxy is not allowed to become a proxy" );
      \_voters.modify( pitr, 0, [&]( auto& p ) {
            p.is_proxy = isproxy;
         });
      propagate_weight_change( *pitr );
   } else {
      \_voters.emplace( proxy, [&]( auto& p ) {
            p.owner  = proxy;
            p.is_proxy = isproxy;
         });
   }
}
 ```
 </br>
 分析投票及相关方法后，开始处理投票的交易动作：
 </br>

 ``` c++
 /**
  * When a user posts we create a record that tracks the total votes and the time it
  * was created. A user can submit this action multiple times, but subsequent calls do
  * nothing.
  *
  * This method only does something when called in the context of the author, if
  * any other contexts are notified
  */
 void apply_social_post() {
    const auto& post   = current_action<post_action>();
    require_auth( post.author );

    eosio_assert( current_context() == post.author, "cannot call from any other context" );

    static post_record& existing;
    if( !Db::get( post.postid, existing ) )
       Db::store( post.postid, post_record( now() ) );
 }

 /**
  * This action is called when a user casts a vote, it requires that this code is executed
  * in the context of both the voter and the author. When executed in the author's context it
  * updates the vote total.  When executed
  */
 void apply_social_vote() {
    const auto& vote  = current_action<vote_action>();
    require_recipient( vote.voter, vote.author );
    disable_context_code( vote.author() ); /// prevent the author's code from rejecting the potentially negative vote

    auto context = current_context();
    auto voter = vote.getVoter();

    if( context == vote.author ) {
       static post_record post;
       eosio_assert( Db::get( vote.postid, post ) > 0, "unable to find post" );
       eosio_assert( now() - post.created < days(7), "cannot vote after 7 days" );
       post.votes += vote.vote_power;
       Db::store( vote.postid, post );
    }
    else if( context == vote.voter ) {
       static account vote_account;
       Db::get( "account", vote_account );
       auto abs_vote = abs(vote.vote_power);
       vote_account.vote_power = min( vote_account.social_power,
                                      vote_account.vote_power + (vote_account.social_power * (now()-last_vote)) / days(7));
       eosio_assert( abs_vote <= vote_account.vote_power, "insufficient vote power" );
       post.votes += vote.vote_power;
       vote_account.vote_power -= abs_vote;
       vote_account.last_vote  = now();
       Db::store( "account", vote_account );
    } else {
       eosio_assert( false, "invalid context for execution of this vote" );
    }
 }
 ```
 </br>
 3、共识
 </br>
 前面的选举过程其实就DPOS的过程，只不过，没有出块，体现不出来它的价值，在EOS的最新版本中采用了BFT-DPOS，所以看下面的数据结构：

 </br>

 ``` c++
 struct block_header_state {
......
    uint32_t                          dpos_proposed_irreversible_blocknum = 0;
    uint32_t                          dpos_irreversible_blocknum = 0;
    uint32_t                          bft_irreversible_blocknum = 0;  //BFT
......
  };

```
 </br>
 这个变量bft_irreversible_blocknum是在push_confirmation中被赋值。connection::blk_send中广播。
 </br>

## 三、出块  
 </br>
出块的代码主要在producer_plugin中：
 </br>

 ``` c++
 producer_plugin_impl::start_block_result producer_plugin_impl::start_block() {
   ......
   //省略各种出块条件的前期判断
   .......
   if (\_pending_block_mode == pending_block_mode::producing) {
   // determine if our watermark excludes us from producing at this point
   if (currrent_watermark_itr != \_producer_watermarks.end()) {
      if (currrent_watermark_itr->second >= hbs->block_num + 1) {
         elog("Not producing block because \"${producer}\" signed a BFT confirmation OR block at a higher block number (${watermark}) than the current fork's head (${head_block_num})",
             ("producer", scheduled_producer.producer_name)
             ("watermark", currrent_watermark_itr->second)
             ("head_block_num", hbs->block_num));
         \_pending_block_mode = pending_block_mode::speculating;
      }
   }
}

try {
   uint16_t blocks_to_confirm = 0;

   if (\_pending_block_mode == pending_block_mode::producing) {
      // determine how many blocks this producer can confirm
      // 1) if it is not a producer from this node, assume no confirmations (we will discard this block anyway)
      // 2) if it is a producer on this node that has never produced, the conservative approach is to assume no
      //    confirmations to make sure we don't double sign after a crash TODO: make these watermarks durable?
      // 3) if it is a producer on this node where this node knows the last block it produced, safely set it -UNLESS-
      // 4) the producer on this node's last watermark is higher (meaning on a different fork)
      if (currrent_watermark_itr != \_producer_watermarks.end()) {
         auto watermark = currrent_watermark_itr->second;
         if (watermark < hbs->block_num) {
            blocks_to_confirm = std::min<uint16_t>(std::numeric_limits<uint16_t>::max(), (uint16_t)(hbs->block_num - watermark));
         }
      }
   }

   chain.abort_block();
   chain.start_block(block_time, blocks_to_confirm);//调用真正的Controller.cpp出块
} FC_LOG_AND_DROP();
......
}       
 //时间调度不断循环出块
 void producer_plugin_impl::schedule_production_loop() {
    chain::controller& chain = app().get_plugin<chain_plugin>().chain();
    \_timer.cancel();
    std::weak_ptr<producer_plugin_impl> weak_this = shared_from_this();

    auto result = start_block();//出块

    if (result == start_block_result::failed) {
       elog("Failed to start a pending block, will try again later");
       \_timer.expires_from_now( boost::posix_time::microseconds( config::block_interval_us  / 10 ));

       // we failed to start a block, so try again later?
       \_timer.async_wait([weak_this,cid=++_timer_corelation_id](const boost::system::error_code& ec) {
          auto self = weak_this.lock();
          if (self && ec != boost::asio::error::operation_aborted && cid == self->_timer_corelation_id) {
             self->schedule_production_loop();
          }
       });
    } else if (\_pending_block_mode == pending_block_mode::producing) {
      \_timer.async_wait([&chain,weak_this,cid=++_timer_corelation_id](const boost::system::error_code& ec) {
        auto self = weak_this.lock();
        if (self && ec != boost::asio::error::operation_aborted && cid == self->_timer_corelation_id) {
           auto res = self->maybe_produce_block();//完成出块
           fc_dlog(\_log, "Producing Block #${num} returned: ${res}", ("num", chain.pending_block_state()->block_num)("res", res) );
        }
     });
......
} else if (\_pending_block_mode == pending_block_mode::speculating && !\_producers.empty() && !production_disabled_by_policy()){
       // if we have any producers then we should at least set a timer for our next available slot
       optional<fc::time_point> wake_up_time;
       for (const auto&p: \_producers) {
          auto next_producer_block_time = calculate_next_block_time(p);
          if (next_producer_block_time) {
             auto producer_wake_up_time = \*next_producer_block_time - fc::microseconds(config::block_interval_us);
             if (wake_up_time) {
                // wake up with a full block interval to the deadline
                wake_up_time = std::min<fc::time_point>(\*wake_up_time, producer_wake_up_time);
             } else {
                wake_up_time = producer_wake_up_time;
             }
          }
       }

       if (wake_up_time) {
.......
       } else {
          ......
       }
    } else {
       fc_dlog(\_log, "Speculative Block Created");
    }
 }

 //在操作中断时启动异步出块
 bool producer_plugin_impl::maybe_produce_block() {
    auto reschedule = fc::make_scoped_exit([this]{
       //退出本范围重新启动正常出块
       schedule_production_loop();
    });

    try {
       produce_block();//出块
       return true;
    } FC_LOG_AND_DROP();

    //处理异常时的出块
    fc_dlog(\_log, "Aborting block due to produce_block error");
    chain::controller& chain = app().get_plugin<chain_plugin>().chain();
    chain.abort_block();
    return false;
 }
 void producer_plugin_impl::produce_block() {
......

   //idump( (fc::time_point::now() - chain.pending_block_time()) );
   chain.finalize_block();// 完成出块---下面是签名和提交块
   chain.sign_block( [&]( const digest_type& d ) {
      auto debug_logger = maybe_make_debug_time_logger();
      return signature_provider_itr->second(d);
   } );
   chain.commit_block();
......
 }
 ```
 </br>
 真正的出块是在controller.hpp.cpp中，需要注意的是按照EOS一惯的风格，真正的代码在controller_impl类中：
 </br>
 ``` c++
 void start_block( block_timestamp_type when, uint16_t confirm_block_count, controller::block_status s ) {
    FC_ASSERT( !pending );

    FC_ASSERT( db.revision() == head->block_num, "",
              ("db.revision()", db.revision())("controller_head_block", head->block_num)("fork_db_head_block", fork_db.head()->block_num) );

    auto guard_pending = fc::make_scoped_exit([this](){
       pending.reset();
    });
    //创建pending，块在其中
    pending = db.start_undo_session(true);

    pending->_block_status = s;

    pending->_pending_block_state = std::make_shared<block_state>( \*head, when ); // promotes pending schedule (if any) to active
    pending->_pending_block_state->in_current_chain = true;

    pending->_pending_block_state->set_confirmed(confirm_block_count);

    auto was_pending_promoted = pending->_pending_block_state->maybe_promote_pending();


    //判断当前的状态并设置相关参数
    const auto& gpo = db.get<global_property_object>();
    if( gpo.proposed_schedule_block_num.valid() && // if there is a proposed schedule that was proposed in a block ...
        ( *gpo.proposed_schedule_block_num <= pending->_pending_block_state->dpos_irreversible_blocknum ) && // ... that has now become irreversible ...
        pending->_pending_block_state->pending_schedule.producers.size() == 0 && // ... and there is room for a new pending schedule ...
        !was_pending_promoted // ... and not just because it was promoted to active at the start of this block, then:
      )
    {
       // Promote proposed schedule to pending schedule.
       if( !replaying ) {
          ilog( "promoting proposed schedule (set in block ${proposed_num}) to pending; current block: ${n} lib: ${lib} schedule: ${schedule} ",
                ("proposed_num", \*gpo.proposed_schedule_block_num)("n", pending->_pending_block_state->block_num)
                ("lib", pending->_pending_block_state->dpos_irreversible_blocknum)
                ("schedule", static_cast<producer_schedule_type>(gpo.proposed_schedule) ) );
       }
       pending->_pending_block_state->set_new_producers( gpo.proposed_schedule );
       db.modify( gpo, [&]( auto& gp ) {
          gp.proposed_schedule_block_num = optional<block_num_type>();
          gp.proposed_schedule.clear();
       });
    }

    try {
      //装填交易的实际数据
       auto onbtrx = std::make_shared<transaction_metadata>( get_on_block_transaction() );
       push_transaction( onbtrx, fc::time_point::maximum(), true, self.get_global_properties().configuration.min_transaction_cpu_usage );
    } catch( const boost::interprocess::bad_alloc& e  ) {
       elog( "on block transaction failed due to a bad allocation" );
       throw;
    } catch( const fc::exception& e ) {
       wlog( "on block transaction failed, but shouldn't impact block generation, system contract needs update" );
       edump((e.to_detail_string()));
    } catch( ... ) {
       wlog( "on block transaction failed, but shouldn't impact block generation, system contract needs update" );
    }

    clear_expired_input_transactions();//清除相关交易
    update_producers_authority();//更新生产者相关的权限
    guard_pending.cancel();//解除锁
 }
 ```
 </br>
 finalize_block 、sign_block、 commit_block 、abort_block等与签名和提交部分的代码都在这个模块中，就不再赘述，看代码就可以了。
 </br>
