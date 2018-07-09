# eos源码分析之八区块及数据结构

做为EOS系列的最后一篇，把区块及相关的数据结构分析一下。虽然在前面的共识中分析过出块这部分，但对EOS的区块结构及一些细节并没有深入进去。
</br>

## 一、区块
EOS的区块设计不同的版本变化很大，这里以4.0的为模板分析，先看一下它的数据结构：
</br>

``` c++
struct block_header
{
   block_timestamp_type             timestamp;
   account_name                     producer;//帐户标识符 13字节

   uint16_t                         confirmed = 1;  

   block_id_type                    previous;//前一块的HASH

   checksum256_type                 transaction_mroot; /// mroot of cycles_summary
   checksum256_type                 action_mroot; /// mroot of all delivered action receipts

   uint32_t                          schedule_version = 0;
   optional<producer_schedule_type>  new_producers;//新生产者
   extensions_type                   header_extensions;


   digest_type       digest()const;//摘要哈希
   block_id_type     id() const;   //自己的哈希
   uint32_t          block_num() const { return num_from_id(previous) + 1; }
   static uint32_t   num_from_id(const block_id_type& id);//ID是任意数字，区块号是从零长到现在的排序号 ID=HASH+n    
};

struct signed_block_header : public block_header
{
   signature_type    producer_signature;//生产者签名
};
struct signed_block : public signed_block_header {
   using signed_block_header::signed_block_header;
   signed_block() = default;
   signed_block( const signed_block_header& h ):signed_block_header(h){}

   vector<transaction_receipt>   transactions; /// new or generated transactions交易记录
   extensions_type               block_extensions;//扩展区
};
using signed_block_ptr = std::shared_ptr<signed_block>;//重定义一个新的数据类型，方便使用
```
</br>
这里感觉最大的不同是把原来的交易ID直接弄成了交易内容，这样有点简单粗暴的感觉，但是确实是容易理解一些。区块的生产在前面选举后分析过，这里不再赘述，看一下产生区块中对交易的处理。
</br>

## 二、交易和上链
</br>
正如所有的区块链一样，交易最终打包入区块，才是真正的区块成功能，也就是说，区块生产出来的目的不是单纯生产块，而要把交易数据打包进去，然后再保存到数据库，最终上链。
</br>

### 1、交易
</br>

``` c++
transaction_trace_ptr push_transaction( const transaction_metadata_ptr& trx,
                                        fc::time_point deadline,
                                        bool implicit,
                                        uint32_t billed_cpu_time_us  )
{
   FC_ASSERT(deadline != fc::time_point(), "deadline cannot be uninitialized");

   transaction_trace_ptr trace;//交易检索
   try {
      transaction_context trx_context(self, trx->trx, trx->id); //交易管理控制
      trx_context.deadline = deadline;
      trx_context.billed_cpu_time_us = billed_cpu_time_us;
      trace = trx_context.trace;
      try {
         if( implicit ) {
            trx_context.init_for_implicit_trx();
         } else {
            trx_context.init_for_input_trx( trx->packed_trx.get_unprunable_size(),
                                            trx->packed_trx.get_prunable_size(),
                                            trx->trx.signatures.size() );
         }

         //检查权限集合
         if( !implicit && pending->_block_status == controller::block_status::incomplete ) {
            check_actor_list( trx_context.bill_to_accounts ); // Assumes bill_to_accounts is the set of actors authorizing the transaction
         }

        //延迟状态
         trx_context.delay = fc::seconds(trx->trx.delay_sec);

         //检查权限，这个前面分析过
         if( !self.skip_auth_check() && !implicit ) {
            authorization.check_authorization(
                    trx->trx.actions,
                    trx->recover_keys( chain_id ),
                    {},
                    trx_context.delay,
                    [](){}
                    /*std::bind(&transaction_context::add_cpu_usage_and_check_time, &trx_context,
                              std::placeholders::_1)*/,
                    false
            );
         }

         //执行上下文,其实就是执行tx中的action
         trx_context.exec();
         trx_context.finalize(); // Automatically rounds up network and CPU usage in trace and bills payers if successful

         //创建恢复点
         auto restore = make_block_restore_point();

         if (!implicit) {
            transaction_receipt::status_enum s = (trx_context.delay == fc::seconds(0))
                                                 ? transaction_receipt::executed
                                                 : transaction_receipt::delayed;
            //交易填充
            trace->receipt = push_receipt(trx->packed_trx, s, trx_context.billed_cpu_time_us, trace->net_usage);
            pending->_pending_block_state->trxs.emplace_back(trx);
         } else {
            transaction_receipt_header r;
            r.status = transaction_receipt::executed;
            r.cpu_usage_us = trx_context.billed_cpu_time_us;
            r.net_usage_words = trace->net_usage / 8;
            trace->receipt = r;
         }
         //填充ACTION
         fc::move_append(pending->_actions, move(trx_context.executed));

         // call the accept signal but only once for this transaction
         if (!trx->accepted) {
            emit( self.accepted_transaction, trx);
            trx->accepted = true;
         }

         emit(self.applied_transaction, trace);// 发送成功打包交易的消息

         trx_context.squash();//不敢肯定，是不是清理回退的数据
         restore.cancel();//取消恢复

         if (!implicit) {
            unapplied_transactions.erase( trx->signed_id );
         }
         return trace;
      } catch (const fc::exception& e) {
         trace->except = e;
         trace->except_ptr = std::current_exception();
      }

      if (!failure_is_subjective(*trace->except)) {
         unapplied_transactions.erase( trx->signed_id );
      }

      return trace;
   } FC_CAPTURE_AND_RETHROW((trace))
}
```
</br>

### 2、上链
</br>
在apply_block中：
</br>

``` c++
void commit_block( bool add_to_fork_db ) {
   if( add_to_fork_db ) {
      pending->_pending_block_state->validated = true;
      auto new_bsp = fork_db.add( pending->_pending_block_state );
      emit( self.accepted_block_header, pending->_pending_block_state );
      head = fork_db.head();
      FC_ASSERT( new_bsp == head, "committed block did not become the new head in fork database" );

   }

//    ilog((fc::json::to_pretty_string(*pending->_pending_block_state->block)));
   emit( self.accepted_block, pending->_pending_block_state );

   if( !replaying ) {
      reversible_blocks.create<reversible_block_object>( [&]( auto& ubo ) {
         ubo.blocknum = pending->_pending_block_state->block_num;
         ubo.set_block( pending->_pending_block_state->block );
      });
   }

   pending->push();
   pending.reset();//恢复状态，可以再次出块

}
```
</br>
通过fork_db的操作把数据库存储起来，然后挂到链上，形成区块链。再广播出去，清除状态，重新准备出块。
</br>
</br>

## 三、相关的几个数据结构

</br>
有几个数据结构比较重要：multi_index,optional和scoped_exit。
</br>
</br>

### 1、访问数据库的multi_index
</br>

``` c++
template<uint64_t TableName, typename T, typename... Indices>
class multi_index
{
   private:

      static_assert( sizeof...(Indices) <= 16, "multi_index only supports a maximum of 16 secondary indices" );

      constexpr static bool validate_table_name( uint64_t n ) {
         // Limit table names to 12 characters so that the last character (4 bits) can be used to distinguish between the secondary indices.
         return (n & 0x000000000000000FULL) == 0;
      }

      constexpr static size_t max_stack_buffer_size = 512;

      static_assert( validate_table_name(TableName), "multi_index does not support table names with a length greater than 12");

      uint64_t _code;
      uint64_t _scope;

      mutable uint64_t _next_primary_key;

      enum next_primary_key_tags : uint64_t {
         no_available_primary_key = static_cast<uint64_t>(-2), // Must be the smallest uint64_t value compared to all other tags
         unset_next_primary_key = static_cast<uint64_t>(-1)
      };

      struct item : public T
      {
         template<typename Constructor>
         item( const multi_index* idx, Constructor&& c )
         :\__idx(idx){
            c(\*this);
         }
......
      };

      struct item_ptr
      {
         item_ptr(std::unique_ptr<item>&& i, uint64_t pk, int32_t pitr)
         : \_item(std::move(i)), \_primary_key(pk), \_primary_itr(pitr) {}

......
      };

      mutable std::vector<item_ptr> _items_vector;

      template<uint64_t IndexName, typename Extractor, uint64_t Number, bool IsConst>
      struct index {
         public:
            typedef Extractor  secondary_extractor_type;
            typedef typename std::decay<decltype( Extractor()(nullptr) )>::type secondary_key_type;
......

            constexpr static uint64_t name()   { return index_table_name; }
            constexpr static uint64_t number() { return Number; }

            struct const_iterator : public std::iterator<std::bidirectional_iterator_tag, const T> {
               public:
                  friend bool operator == ( const const_iterator& a, const const_iterator& b ) {
                     return a.\_item == b.\_item;
                  }
                  friend bool operator != ( const const_iterator& a, const const_iterator& b ) {
                     return a.\_item != b.\_item;
                  }

                  const T& operator*()const { return *static_cast<const T*>(\_item); }
                  const T* operator->()const { return static_cast<const T*>(\_item); }

......

                     return *this;
                  }

                  const_iterator& operator--() {
                     using namespace \_multi_index_detail;

......

                     return \*this;
                  }

                  const_iterator():_item(nullptr){}
               private:
                  friend struct index;
                  const_iterator( const index* idx, const item* i = nullptr )
                  : _idx(idx), _item(i) {}

                  const index* _idx;
                  const item*  _item;
            }; /// struct multi_index::index::const_iterator

            typedef std::reverse_iterator<const_iterator> const_reverse_iterator;

            const_iterator cbegin()const {
               using namespace \_multi_index_detail;
               return lower_bound( secondary_key_traits<secondary_key_type>::lowest() );
            }
......

            const T& get( secondary_key_type&& secondary, const char* error_msg = "unable to find secondary key" )const {
               return get( secondary, error_msg );
            }

            // Gets the object with the smallest primary key in the case where the secondary key is not unique.
            const T& get( const secondary_key_type& secondary, const char* error_msg = "unable to find secondary key" )const {
               auto result = find( secondary );
               eosio_assert( result != cend(), error_msg );
               return *result;
            }

            const_iterator lower_bound( secondary_key_type&& secondary )const {
               return lower_bound( secondary );
            }
            const_iterator lower_bound( const secondary_key_type& secondary )const {
               using namespace \_multi_index_detail;
......

               return {this, &mi};
            }

            const_iterator upper_bound( secondary_key_type&& secondary )const {
               return upper_bound( secondary );
            }
            const_iterator upper_bound( const secondary_key_type& secondary )const {
......

               return {this, &mi};
            }

            const_iterator iterator_to( const T& obj ) {
......
               return {this, &objitem};
            }
......

            static auto extract_secondary_key(const T& obj) { return secondary_extractor_type()(obj); }

         private:
            friend class multi_index;

            index( typename std::conditional<IsConst, const multi_index*, multi_index*>::type midx )
            :_multidx(midx){}

            typename std::conditional<IsConst, const multi_index*, multi_index*>::type _multidx;
      }; /// struct multi_index::index

......
         const item* ptr = itm.get();
         auto pk   = itm->primary_key();
         auto pitr = itm->__primary_itr;

         _items_vector.emplace_back( std::move(itm), pk, pitr );

         return *ptr;
      } /// load_object_by_primary_iterator

   public:

      multi_index( uint64_t code, uint64_t scope )
      :_code(code),_scope(scope),_next_primary_key(unset_next_primary_key)
      {}

......

            _item = &_multidx->load_object_by_primary_iterator( prev_itr );
            return *this;
         }

         private:
            const_iterator( const multi_index* mi, const item* i = nullptr )
            :_multidx(mi),_item(i){}

            const multi_index* _multidx;
            const item*        _item;
            friend class multi_index;
      }; /// struct multi_index::const_iterator

      typedef std::reverse_iterator<const_iterator> const_reverse_iterator;

      const_iterator cbegin()const {
         return lower_bound(std::numeric_limits<uint64_t>::lowest());
      }
      const_iterator begin()const  { return cbegin(); }

.......

      void erase( const T& obj ) {
         using namespace \_multi_index_detail;

......

         hana::for_each( \_indices, [&]( auto& idx ) {
            typedef typename decltype(+hana::at_c<0>(idx))::type index_type;

            auto i = objitem.__iters[index_type::number()];
            if( i < 0 ) {
              typename index_type::secondary_key_type secondary;
              i = secondary_index_db_functions<typename index_type::secondary_key_type>::db_idx_find_primary( \_code, \_scope, index_type::name(), objitem.primary_key(),  secondary );
            }
            if( i >= 0 )
               secondary_index_db_functions<typename index_type::secondary_key_type>::db_idx_remove( i );
         });
      }

};

```
</br>
multi_index这个数据结构同样是仿照BOOST库中的boost::multi_index;估计EOS的开发人员觉得这个太重，自己搞了一个，当然，顺带实现很多自己独立的需求。需要说明的是WIKI上的说明是比较落后的，而且EOS开发团队也声明了，这个容器对象是不断演进的，所以说现在分析的可能已经是落后的了，但可能他们的大原则不会有剧烈的变动。
</br>
EOS为每个账户都预留了数据库空间（大小与代币持有量有关），账户可以建立多个数据表。智能合约无法直接操作存储在见证人硬盘中的数据表，需要使用multi_index作为中间工具（或者叫容器），每个multi_index实例都与一个特定账户的特定数据表进行交互（取决于实例化时的参数）。
</br>
这个多索引表有几个特点：类似ORM中的映射表，行为独立的对象，列为属性；有主键和非主键，排序时默认为升序，同样主键只能唯一并为uint64_t类型；支持自定函数做为索引，但返回值受限，即只能为支持的键类型；允许多索引排序，但是二级索引不大于16，前面的代码可以看到，同时不支持二级索引的直接构建；类似双向链表可以双向迭代。
</br>
它支持主要以下几种操作：
</br>
emplace:添加一个对象（row）到表中，返回一个新创建的主键迭代器。在这个过程中创建新对象，序列化写入表中，更新二级索引，付费。如果出现异常则直接抛出。
</br>
erase:这个就简单了，直接擦除。可以用迭代器也可以引用对象来删除。删除后返回之后的迭代器，并更新相关索引及费用。
</br>
modify:类似于数据库的UPDATE，这个比较麻烦，需要提供更新对象的迭代器，更新对象的引用，帐户（需要付费的）以及更新目标对象的函数（lambada）,无返回值，在操作过程中主要是要对payer的属性进行判断，然后进行费用的计算和相关退费，完成后更新索引。
</br>
</br>
get:由主键查找对象，返回对象的引用，如果没找到，抛出异常。
</br>
find:根据主键查找已存在的对象。它的返回值是一个迭代器。如果没有查到返回一个end迭代器。
</br>
迭代器有点类似于STD标准库的迭代器，可以前后遍历，这里不再赘述。

</br>

### 2、类boost::optional的自定义容器
</br>

``` c++

/**
 *  @brief provides stack-based nullable value similar to boost::optional
 *
 *  Simply including boost::optional adds 35,000 lines to each object file, using
 *  fc::optional adds less than 400.
 */
template<typename T>
class optional
{
  public:
    typedef T value_type;
    typedef typename std::aligned_storage<sizeof(T), alignof(T)>::type storage_type;

    optional():\_valid(false){}
    ~optional(){ reset(); }

    optional( optional& o )
    :_valid(false)
    {
      if( o._valid ) new (ptr()) T( *o );
      \_valid = o._valid;
    }

......

    template<typename U>
    optional( const optional<U>& o )
    :_valid(false)
    {
      if( o._valid ) new (ptr()) T( *o );
      \_valid = o._valid;
    }

    template<typename U>
    optional( optional<U>& o )
    :_valid(false)
    {
      if( o._valid )
      {
        new (ptr()) T( *o );
      }
      \_valid = o._valid;
    }

    template<typename U>
    optional( optional<U>&& o )
    :_valid(false)
    {
      if( o._valid ) new (ptr()) T( fc::move(*o) );
      \_valid = o._valid;
      o.reset();
    }

    ......

    optional& operator=( optional&& o )
    {
      if (this != &o)
      {
        if( \_valid && o._valid )
        {
          ref() = fc::move(*o);
          o.reset();
        } else if ( !\_valid && o._valid ) {
          \*this = fc::move(*o);
        } else if (\_valid) {
          reset();
        }
      }
      return \*this;
    }


    friend bool operator < ( const optional a, optional b )
    {
       if( a.valid() && b.valid() ) return \*a < \*b;
       return a.valid() < b.valid();
    }
......

    void     reset()
    {
        if( \_valid )
        {
            ref().~T(); // cal destructor
        }
        \_valid = false;
    }
  private:
    template<typename U> friend class optional;
    T&       ref()      { return \*ptr(); }
    const T& ref()const { return *ptr(); }
    T*       ptr()      { return reinterpret_cast<T*>(&\_value);  }
    const T* ptr()const { return reinterpret_cast<const T\*>(&\_value); }

    bool         _valid;
    storage_type _value;
};
```
</br>
这个其实不能称做一个容器，因为它一般只盛放一个数据结构，它的主要目的标题也很清楚，其实是老大们不愿意使用BOOST的相关代码，太多了，这个才几百行，小巧实用。
</br>
这个模板类的主要作用是封装一些数据结构，防止未初始化或者无意义的数据表达不清楚。比如一些返回值是NULL，有EOF，还有一些是string::npos等等，封装起来就是为了起一个标准的作用，其实你看这个类内部，并没有太多的真正意义的自己操作的数据，大多还是原生数据结构的使用。
</br>

### 3、范围控制的scoped_exit
</br>

``` c++
template<typename Callback>
class scoped_exit {
   public:
      template<typename C>
      scoped_exit( C&& c ):callback( std::forward<C>(c) ){}

      scoped_exit( scoped_exit&& mv )
      :callback( std::move( mv.callback ) ),canceled(mv.canceled)
      {
         mv.canceled = true;
      }

      scoped_exit( const scoped_exit& ) = delete;
      scoped_exit& operator=( const scoped_exit& ) = delete;

      ~scoped_exit() {
         if (!canceled)
            try { callback(); } catch( ... ) {}
      }

      scoped_exit& operator = ( scoped_exit&& mv ) {
         if( this != &mv ) {
            ~scoped_exit();
            callback = std::move(mv.callback);
            canceled = mv.canceled;
            mv.canceled = true;
         }

         return \*this;
      }

      void cancel() { canceled = true; }

   private:
      Callback callback;
      bool canceled = false;
};

template<typename Callback>
scoped_exit<Callback> make_scoped_exit( Callback&& c ) {
   return scoped_exit<Callback>( std::forward<Callback>(c) );
}
```
</br>
这个类其实也得很有趣，如果对RAII比较了解的话，这个其实有一点变相的意思，在离开某个范围时，调用这个数据结构的析构函数，然后调用指定的回调函数来处理一些相关的事情，比如清理一些内存等等。
</br>
这里的模板构造函数用到了std::forward<C>(c)完美转发，将左右值的匹配自动完成。一些小细节处理的相当不错。
</br>
其实EOS中的数据结构和编程方式还是有些复杂的，特别是其中一些使用了比较传统的宏模板自动创建的方法（在MFC中常见，但广受诟病），所以一些代码还是比较晦涩的，不建议也这样使用。
</br>
