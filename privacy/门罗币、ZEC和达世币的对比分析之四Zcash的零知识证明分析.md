# 门罗币、ZEC和达世币的对比分析之四Zcash的零知识证明分析

## 一、Zcash特点
Zcah的主要源码是从比特币转过来的。所以说可以把它看成比特币的的一个分支。这里需要说明的是，一定要把Zcash和Zcoin区别开来。两者都使用了零知识证明。只不过二者使用的零知识证明的算法不同，Zcash使用的是libsnark的相关算法。
</br>
相对于其它匿名方式，使用零知识证明的方式可以说是最优的。但是零知识证明的交互式证明的方式，却在无形间增加了整个交易处理的时间。同时，使用的信任机制中，还是存在着恶意串通的可能。不过Zcash中使用的零知识证明算法是不需要交互的，不过多轮的验证仍然使它耗费的时间很多（30~40秒，不过具说目前减化版已经缩小到了7秒）。
</br>
相对于其它算法，zkSNARKs算法的应用时间还是比较短，尚需要进一步的验证其它安全性和合理性。

## 二、零知识证明的原理

目前的零知识证明主要有两大类，分为Bulletproofs和rangeproofs。而Zcash使用的是后者。前者据说比后者要更快更安全，但仍然没有生产性的环节进行验证，也就是说，所以有工作仍然是纸面上的。
</br>
零知识证明的数学方式其实就是NP的问题。也就是说，把一个问题通过某种手段可以转换成一个多项式时间内的验证的问题（求解是P）。而Zcash使用的算法适合于QAP问题（不必计较，这个其实是数学上经典的二次分配问题）。
</br>
Goldreich等人已经证明了任何NP成员问题都有零知识证明系统，因此其在密码学中的应用日益广泛。下面简述一下零知识证明的数学赛程：
</br>
1、QAP问题的转化。
</br>
2、NP问题的转化。
</br>
3、利用拉格朗日插值法进行多项式的处理。
</br>
4、抽样点的数学验证。
</br>
5、抽样点的同态映射保护。
</br>
6、KCA（Knowledge of Coefficient Test and Assumption）：强制按约定验证。
</br>
在同态映射保护中，目前更好的方法还有双线性映射和椭圆曲线的方式。不过，方法越好，可能复杂度就越高。到实践应用还需要更好的进行算法的优化。
</br>
更具体的说明请查看相关的算法：
SCIPR实验室的libsnark：https://github.com/scipr-lab/libsnark。
</br>
Zcash修改后的libsnark：https://github.com/zcash/libsnark。

## 三、Zcash中对零知识证明的应用
zk-SNARK是“zero knowledge Succinct Non-interactive ARgument of Knowledge”的缩写，它有三个显著的特点：
</br>
1、零知识：证明过程不透露任何消息。
</br>
2、简洁：不涉及大量数据传输和验证。
</br>
3、无交互：不像网上的阿里巴巴等的例子，需要不断的进行交互问答。
</br>
这里只说明匿名交易，对透明交易不处理。
</br>
在Zcashk，一个交易的输入和输出都是若干note。为描述方便起见，将note记为“note=(PK, v, r)”，其中，PK是所有者的公钥（地址），v是金额，而r是可以唯一区分该note的序列号。输入、输出不再是明文的note，而分别是note的废止通知和签发通知：
</br>
签发通知（note commitment）：作为交易的输出，表示一张新note被签发。一个有效的commitment是一张note存在的证明，然而从它包含的信息中并不知道是哪张note，也就无法知道所有者是谁，金额多少。为满足这一点，最简单的方法是对note的描述信息取哈希，因此note对应的commitment可以简单描述为“HASH(note)”。
</br>
废止通知（note nullifier）：作为交易的输入，表示一张老支票将作废（因为马上要被兑现、花掉了）。同比特币一样，一个交易的输入一定是另一个交易的输出，因此nullifier对应唯一一个commitment（结合commitment的定义，也就唯一对应一张note)，但从它包含的信息并不能推导出是哪个commitment（如果可以的话，ZCash交易便可被追踪，因而丧失隐私性了）。为构造满足要求的nullifier，取哈希依然是个好办法，因此序号为r的note，对应的nullifier可描述为“HASH(r)”。
</br>
通过引入nullifier和commitment，交易之间的种种表现出来的实际的内容，变成了一种互相的心知肚明。区块链的共识者各自维护一个nullifer和commitment的集合，这个集合会根据交易的不同时间进行动态的变化。。
</br>
当广播消息来到，节点会通过二者进行验证和处理，同时使用零知识证明来控制权限的使用（也即支付或者兑现的权限）。
</br>

## 四、源码分析
在Zcash中，使用了libsnark的库，所以，零知识证明是围绕着库的调用展开的。这里分析一下这个库的源码，在原来的标准的零知识证明库中有两个版本的生成，这里只使用了gadgetbli1.先看一下初步的上层调用：
</br>

```C++
template<typename FieldT, size_t NumInputs, size_t NumOutputs>
class joinsplit_gadget : gadget<FieldT> {
private:
    // Verifier inputs
    pb_variable_array<FieldT> zk_packed_inputs;
    pb_variable_array<FieldT> zk_unpacked_inputs;
    std::shared_ptr<multipacking_gadget<FieldT>> unpacker;

    std::shared_ptr<digest_variable<FieldT>> zk_merkle_root;
    std::shared_ptr<digest_variable<FieldT>> zk_h_sig;
    boost::array<std::shared_ptr<digest_variable<FieldT>>, NumInputs> zk_input_nullifiers;
    boost::array<std::shared_ptr<digest_variable<FieldT>>, NumInputs> zk_input_macs;
    boost::array<std::shared_ptr<digest_variable<FieldT>>, NumOutputs> zk_output_commitments;
    pb_variable_array<FieldT> zk_vpub_old;
    pb_variable_array<FieldT> zk_vpub_new;

    // Aux inputs
    pb_variable<FieldT> ZERO;
    std::shared_ptr<digest_variable<FieldT>> zk_phi;
    pb_variable_array<FieldT> zk_total_uint64;

    // Input note gadgets
    boost::array<std::shared_ptr<input_note_gadget<FieldT>>, NumInputs> zk_input_notes;
    boost::array<std::shared_ptr<PRF_pk_gadget<FieldT>>, NumInputs> zk_mac_authentication;

    // Output note gadgets
    boost::array<std::shared_ptr<output_note_gadget<FieldT>>, NumOutputs> zk_output_notes;

public:
    // PRF_pk only has a 1-bit domain separation "nonce"
    // for different macs.
    BOOST_STATIC_ASSERT(NumInputs <= 2);

    // PRF_rho only has a 1-bit domain separation "nonce"
    // for different output `rho`.
    BOOST_STATIC_ASSERT(NumOutputs <= 2);

    joinsplit_gadget(protoboard<FieldT> &pb) : gadget<FieldT>(pb) {
        // Verification
        {
            // The verification inputs are all bit-strings of various
            // lengths (256-bit digests and 64-bit integers) and so we
            // pack them into as few field elements as possible. (The
            // more verification inputs you have, the more expensive
            // verification is.)
            zk_packed_inputs.allocate(pb, verifying_field_element_size());
            pb.set_input_sizes(verifying_field_element_size());

            alloc_uint256(zk_unpacked_inputs, zk_merkle_root);
            alloc_uint256(zk_unpacked_inputs, zk_h_sig);

            for (size_t i = 0; i < NumInputs; i++) {
                alloc_uint256(zk_unpacked_inputs, zk_input_nullifiers[i]);
                alloc_uint256(zk_unpacked_inputs, zk_input_macs[i]);
            }

            for (size_t i = 0; i < NumOutputs; i++) {
                alloc_uint256(zk_unpacked_inputs, zk_output_commitments[i]);
            }

            alloc_uint64(zk_unpacked_inputs, zk_vpub_old);
            alloc_uint64(zk_unpacked_inputs, zk_vpub_new);

            assert(zk_unpacked_inputs.size() == verifying_input_bit_size());

            // This gadget will ensure that all of the inputs we provide are
            // boolean constrained.
            unpacker.reset(new multipacking_gadget<FieldT>(
                pb,
                zk_unpacked_inputs,
                zk_packed_inputs,
                FieldT::capacity(),
                "unpacker"
            ));
        }

        // We need a constant "zero" variable in some contexts. In theory
        // it should never be necessary, but libsnark does not synthesize
        // optimal circuits.
        //
        // The first variable of our constraint system is constrained
        // to be one automatically for us, and is known as `ONE`.
        ZERO.allocate(pb);

        zk_phi.reset(new digest_variable<FieldT>(pb, 252, ""));

        zk_total_uint64.allocate(pb, 64);

        for (size_t i = 0; i < NumInputs; i++) {
            // Input note gadget for commitments, macs, nullifiers,
            // and spend authority.
            zk_input_notes[i].reset(new input_note_gadget<FieldT>(
                pb,
                ZERO,
                zk_input_nullifiers[i],
                *zk_merkle_root
            ));

            // The input keys authenticate h_sig to prevent
            // malleability.
            zk_mac_authentication[i].reset(new PRF_pk_gadget<FieldT>(
                pb,
                ZERO,
                zk_input_notes[i]->a_sk->bits,
                zk_h_sig->bits,
                i ? true : false,
                zk_input_macs[i]
            ));
        }

        for (size_t i = 0; i < NumOutputs; i++) {
            zk_output_notes[i].reset(new output_note_gadget<FieldT>(
                pb,
                ZERO,
                zk_phi->bits,
                zk_h_sig->bits,
                i ? true : false,
                zk_output_commitments[i]
            ));
        }
    }

    void generate_r1cs_constraints() {
        // The true passed here ensures all the inputs
        // are boolean constrained.
        unpacker->generate_r1cs_constraints(true);

        // Constrain `ZERO`
        generate_r1cs_equals_const_constraint<FieldT>(this->pb, ZERO, FieldT::zero(), "ZERO");

        // Constrain bitness of phi
        zk_phi->generate_r1cs_constraints();

        for (size_t i = 0; i < NumInputs; i++) {
            // Constrain the JoinSplit input constraints.
            zk_input_notes[i]->generate_r1cs_constraints();

            // Authenticate h_sig with a_sk
            zk_mac_authentication[i]->generate_r1cs_constraints();
        }

        for (size_t i = 0; i < NumOutputs; i++) {
            // Constrain the JoinSplit output constraints.
            zk_output_notes[i]->generate_r1cs_constraints();
        }

        // Value balance
        {
            linear_combination<FieldT> left_side = packed_addition(zk_vpub_old);
            for (size_t i = 0; i < NumInputs; i++) {
                left_side = left_side + packed_addition(zk_input_notes[i]->value);
            }

            linear_combination<FieldT> right_side = packed_addition(zk_vpub_new);
            for (size_t i = 0; i < NumOutputs; i++) {
                right_side = right_side + packed_addition(zk_output_notes[i]->value);
            }

            // Ensure that both sides are equal
            this->pb.add_r1cs_constraint(r1cs_constraint<FieldT>(
                1,
                left_side,
                right_side
            ));

            // #854: Ensure that left_side is a 64-bit integer.
            for (size_t i = 0; i < 64; i++) {
                generate_boolean_r1cs_constraint<FieldT>(
                    this->pb,
                    zk_total_uint64[i],
                    ""
                );
            }

            this->pb.add_r1cs_constraint(r1cs_constraint<FieldT>(
                1,
                left_side,
                packed_addition(zk_total_uint64)
            ));
        }
    }

    void generate_r1cs_witness(
        const uint252& phi,
        const uint256& rt,
        const uint256& h_sig,
        const boost::array<JSInput, NumInputs>& inputs,
        const boost::array<SproutNote, NumOutputs>& outputs,
        uint64_t vpub_old,
        uint64_t vpub_new
    ) {
        // Witness `zero`
        this->pb.val(ZERO) = FieldT::zero();

        // Witness rt. This is not a sanity check.
        //
        // This ensures the read gadget constrains
        // the intended root in the event that
        // both inputs are zero-valued.
        zk_merkle_root->bits.fill_with_bits(
            this->pb,
            uint256_to_bool_vector(rt)
        );

        // Witness public balance values
        zk_vpub_old.fill_with_bits(
            this->pb,
            uint64_to_bool_vector(vpub_old)
        );
        zk_vpub_new.fill_with_bits(
            this->pb,
            uint64_to_bool_vector(vpub_new)
        );

        {
            // Witness total_uint64 bits
            uint64_t left_side_acc = vpub_old;
            for (size_t i = 0; i < NumInputs; i++) {
                left_side_acc += inputs[i].note.value();
            }

            zk_total_uint64.fill_with_bits(
                this->pb,
                uint64_to_bool_vector(left_side_acc)
            );
        }

        // Witness phi
        zk_phi->bits.fill_with_bits(
            this->pb,
            uint252_to_bool_vector(phi)
        );

        // Witness h_sig
        zk_h_sig->bits.fill_with_bits(
            this->pb,
            uint256_to_bool_vector(h_sig)
        );

        for (size_t i = 0; i < NumInputs; i++) {
            // Witness the input information.
            auto merkle_path = inputs[i].witness.path();
            zk_input_notes[i]->generate_r1cs_witness(
                merkle_path,
                inputs[i].key,
                inputs[i].note
            );

            // Witness macs
            zk_mac_authentication[i]->generate_r1cs_witness();
        }

        for (size_t i = 0; i < NumOutputs; i++) {
            // Witness the output information.
            zk_output_notes[i]->generate_r1cs_witness(outputs[i]);
        }

        // [SANITY CHECK] Ensure that the intended root
        // was witnessed by the inputs, even if the read
        // gadget overwrote it. This allows the prover to
        // fail instead of the verifier, in the event that
        // the roots of the inputs do not match the
        // treestate provided to the proving API.
        zk_merkle_root->bits.fill_with_bits(
            this->pb,
            uint256_to_bool_vector(rt)
        );

        // This happens last, because only by now are all the
        // verifier inputs resolved.
        unpacker->generate_r1cs_witness_from_bits();
    }

```
</br>
通过名字来看，它和库内部的函数名字操持一致，这几个函数主要用来提供处理交易前的数据，深入到库内部看一下相关的函数：
</br>

```C++
template<typename FieldT>
void generate_boolean_r1cs_constraint(protoboard<FieldT> &pb, const pb_linear_combination<FieldT> &lc, const std::string &annotation_prefix)
/* forces lc to take value 0 or 1 by adding constraint lc * (1-lc) = 0 */
{
    pb.add_r1cs_constraint(r1cs_constraint<FieldT>(lc, 1-lc, 0),
                           FMT(annotation_prefix, " boolean_r1cs_constraint"));
}

template<typename FieldT>
void generate_r1cs_equals_const_constraint(protoboard<FieldT> &pb, const pb_linear_combination<FieldT> &lc, const FieldT& c, const std::string &annotation_prefix)
{
    pb.add_r1cs_constraint(r1cs_constraint<FieldT>(1, lc, c),
                           FMT(annotation_prefix, " constness_constraint"));
}

template<typename FieldT>
void packing_gadget<FieldT>::generate_r1cs_constraints(const bool enforce_bitness)
/* adds constraint result = \sum  bits[i] * 2^i */
{
    this->pb.add_r1cs_constraint(r1cs_constraint<FieldT>(1, pb_packing_sum<FieldT>(bits), packed), FMT(this->annotation_prefix, " packing_constraint"));

    if (enforce_bitness)
    {
        for (size_t i = 0; i < bits.size(); ++i)
        {
            generate_boolean_r1cs_constraint<FieldT>(this->pb, bits[i], FMT(this->annotation_prefix, " bitness_%zu", i));
        }
    }
}

template<typename FieldT>
void field_vector_copy_gadget<FieldT>::generate_r1cs_witness()
{
    do_copy.evaluate(this->pb);
    assert(this->pb.lc_val(do_copy) == FieldT::one() || this->pb.lc_val(do_copy) == FieldT::zero());
    if (this->pb.lc_val(do_copy) != FieldT::zero())
    {
        for (size_t i = 0; i < source.size(); ++i)
        {
            this->pb.val(target[i]) = this->pb.val(source[i]);
        }
    }
}
```
</br>
库中针对不同的情况展开了很多的重载函数，这里就不一一的列出了。然后需要进行QAP和NP的处理：
</br>

```C++
template<typename FieldT>
qap_instance<FieldT> r1cs_to_qap_instance_map(const r1cs_constraint_system<FieldT> &cs)
{
    enter_block("Call to r1cs_to_qap_instance_map");

    const std::shared_ptr<evaluation_domain<FieldT> > domain = get_evaluation_domain<FieldT>(cs.num_constraints() + cs.num_inputs() + 1);

    std::vector<std::map<size_t, FieldT> > A_in_Lagrange_basis(cs.num_variables()+1);
    std::vector<std::map<size_t, FieldT> > B_in_Lagrange_basis(cs.num_variables()+1);
    std::vector<std::map<size_t, FieldT> > C_in_Lagrange_basis(cs.num_variables()+1);

    enter_block("Compute polynomials A, B, C in Lagrange basis");
    /**
     * add and process the constraints
     *     input_i * 0 = 0
     * to ensure soundness of input consistency
     \*/
    for (size_t i = 0; i <= cs.num_inputs(); ++i)
    {
        A_in_Lagrange_basis[i][cs.num_constraints() + i] = FieldT::one();
    }
    /* process all other constraints \*/
    for (size_t i = 0; i < cs.num_constraints(); ++i)
    {
        for (size_t j = 0; j < cs.constraints[i].a.terms.size(); ++j)
        {
            A_in_Lagrange_basis[cs.constraints[i].a.terms[j].index][i] +=
                cs.constraints[i].a.terms[j].coeff;
        }

        for (size_t j = 0; j < cs.constraints[i].b.terms.size(); ++j)
        {
            B_in_Lagrange_basis[cs.constraints[i].b.terms[j].index][i] +=
                cs.constraints[i].b.terms[j].coeff;
        }

        for (size_t j = 0; j < cs.constraints[i].c.terms.size(); ++j)
        {
            C_in_Lagrange_basis[cs.constraints[i].c.terms[j].index][i] +=
                cs.constraints[i].c.terms[j].coeff;
        }
    }
    leave_block("Compute polynomials A, B, C in Lagrange basis");

    leave_block("Call to r1cs_to_qap_instance_map");

    return qap_instance<FieldT>(domain,
                                cs.num_variables(),
                                domain->m,
                                cs.num_inputs(),
                                std::move(A_in_Lagrange_basis),
                                std::move(B_in_Lagrange_basis),
                                std::move(C_in_Lagrange_basis));
}

template<typename FieldT>
size_t r1cs_constraint_system<FieldT>::num_inputs() const
{
    return primary_input_size;
}

template<typename FieldT>
size_t r1cs_constraint_system<FieldT>::num_variables() const
{
    return primary_input_size + auxiliary_input_size;
}


template<typename FieldT>
size_t r1cs_constraint_system<FieldT>::num_constraints() const
{
    return constraints.size();
}

template<typename FieldT>
bool r1cs_constraint_system<FieldT>::is_valid() const
{
    if (this->num_inputs() > this->num_variables()) return false;

    for (size_t c = 0; c < constraints.size(); ++c)
    {
        if (!(constraints[c].a.is_valid(this->num_variables()) &&
              constraints[c].b.is_valid(this->num_variables()) &&
              constraints[c].c.is_valid(this->num_variables())))
        {
            return false;
        }
    }

    return true;
}

template<typename FieldT>
void dump_r1cs_constraint(const r1cs_constraint<FieldT> &constraint,
                          const r1cs_variable_assignment<FieldT> &full_variable_assignment,
                          const std::map<size_t, std::string> &variable_annotations)
{
    printf("terms for a:\n"); constraint.a.print_with_assignment(full_variable_assignment, variable_annotations);
    printf("terms for b:\n"); constraint.b.print_with_assignment(full_variable_assignment, variable_annotations);
    printf("terms for c:\n"); constraint.c.print_with_assignment(full_variable_assignment, variable_annotations);
}
```
</br>
这两个问题的主要代码在relations路径目录下，有QAP和R1CS两个部分。这个涉及到比较复杂的数学知识，这里不展开了，别误导大家。
</br>
验证接口在zk_proof_systems目录下，它会调用相关的验证函数进行对上面的多项式的验证。
</br>

```C++
template<typename ppT>
bool r1cs_ppzksnark_verifier_weak_IC(const r1cs_ppzksnark_verification_key<ppT> &vk,
                                     const r1cs_ppzksnark_primary_input<ppT> &primary_input,
                                     const r1cs_ppzksnark_proof<ppT> &proof)
{
    enter_block("Call to r1cs_ppzksnark_verifier_weak_IC");
    r1cs_ppzksnark_processed_verification_key<ppT> pvk = r1cs_ppzksnark_verifier_process_vk<ppT>(vk);
    bool result = r1cs_ppzksnark_online_verifier_weak_IC<ppT>(pvk, primary_input, proof);
    leave_block("Call to r1cs_ppzksnark_verifier_weak_IC");
    return result;
}

template<typename ppT>
bool r1cs_ppzksnark_online_verifier_strong_IC(const r1cs_ppzksnark_processed_verification_key<ppT> &pvk,
                                              const r1cs_ppzksnark_primary_input<ppT> &primary_input,
                                              const r1cs_ppzksnark_proof<ppT> &proof)
{
    bool result = true;
    enter_block("Call to r1cs_ppzksnark_online_verifier_strong_IC");

    if (pvk.encoded_IC_query.domain_size() != primary_input.size())
    {
        print_indent(); printf("Input length differs from expected (got %zu, expected %zu).\n", primary_input.size(), pvk.encoded_IC_query.domain_size());
        result = false;
    }
    else
    {
        result = r1cs_ppzksnark_online_verifier_weak_IC(pvk, primary_input, proof);
    }

    leave_block("Call to r1cs_ppzksnark_online_verifier_strong_IC");
    return result;
}

template<typename ppT>
bool r1cs_ppzksnark_verifier_strong_IC(const r1cs_ppzksnark_verification_key<ppT> &vk,
                                       const r1cs_ppzksnark_primary_input<ppT> &primary_input,
                                       const r1cs_ppzksnark_proof<ppT> &proof)
{
    enter_block("Call to r1cs_ppzksnark_verifier_strong_IC");
    r1cs_ppzksnark_processed_verification_key<ppT> pvk = r1cs_ppzksnark_verifier_process_vk<ppT>(vk);
    bool result = r1cs_ppzksnark_online_verifier_strong_IC<ppT>(pvk, primary_input, proof);
    leave_block("Call to r1cs_ppzksnark_verifier_strong_IC");
    return result;
}
```
</br>
在这其中，还有相关的代码，可以去看源码。
</br>

```C++
template<size_t NumInputs, size_t NumOutputs>
class JoinSplitCircuit : public JoinSplit<NumInputs, NumOutputs> {
public:
    typedef default_r1cs_ppzksnark_pp ppzksnark_ppT;
    typedef Fr<ppzksnark_ppT> FieldT;

    r1cs_ppzksnark_verification_key<ppzksnark_ppT> vk;
    r1cs_ppzksnark_processed_verification_key<ppzksnark_ppT> vk_precomp;
    std::string pkPath;

    JoinSplitCircuit(const std::string vkPath, const std::string pkPath) : pkPath(pkPath) {
        loadFromFile(vkPath, vk);
        vk_precomp = r1cs_ppzksnark_verifier_process_vk(vk);
    }
    ~JoinSplitCircuit() {}

    static void generate(const std::string r1csPath,
                         const std::string vkPath,
                         const std::string pkPath)
    {
        protoboard<FieldT> pb;

        joinsplit_gadget<FieldT, NumInputs, NumOutputs> g(pb);
        g.generate_r1cs_constraints();

        auto r1cs = pb.get_constraint_system();

        saveToFile(r1csPath, r1cs);

        r1cs_ppzksnark_keypair<ppzksnark_ppT> keypair = r1cs_ppzksnark_generator<ppzksnark_ppT>(r1cs);

        saveToFile(vkPath, keypair.vk);
        saveToFile(pkPath, keypair.pk);
    }

    bool verify(
        const ZCProof& proof,
        ProofVerifier& verifier,
        const uint256& pubKeyHash,
        const uint256& randomSeed,
        const boost::array<uint256, NumInputs>& macs,
        const boost::array<uint256, NumInputs>& nullifiers,
        const boost::array<uint256, NumOutputs>& commitments,
        uint64_t vpub_old,
        uint64_t vpub_new,
        const uint256& rt
    ) {
        try {
            auto r1cs_proof = proof.to_libsnark_proof<r1cs_ppzksnark_proof<ppzksnark_ppT>>();

            uint256 h_sig = this->h_sig(randomSeed, nullifiers, pubKeyHash);

            auto witness = joinsplit_gadget<FieldT, NumInputs, NumOutputs>::witness_map(
                rt,
                h_sig,
                macs,
                nullifiers,
                commitments,
                vpub_old,
                vpub_new
            );

            return verifier.check(
                vk,
                vk_precomp,
                witness,
                r1cs_proof
            );
        } catch (...) {
            return false;
        }
    }

    SproutProof prove(
        bool makeGrothProof,
        const boost::array<JSInput, NumInputs>& inputs,
        const boost::array<JSOutput, NumOutputs>& outputs,
        boost::array<SproutNote, NumOutputs>& out_notes,
        boost::array<ZCNoteEncryption::Ciphertext, NumOutputs>& out_ciphertexts,
        uint256& out_ephemeralKey,
        const uint256& pubKeyHash,
        uint256& out_randomSeed,
        boost::array<uint256, NumInputs>& out_macs,
        boost::array<uint256, NumInputs>& out_nullifiers,
        boost::array<uint256, NumOutputs>& out_commitments,
        uint64_t vpub_old,
        uint64_t vpub_new,
        const uint256& rt,
        bool computeProof,
        uint256 *out_esk // Payment disclosure
    ) {
        if (vpub_old > MAX_MONEY) {
            throw std::invalid_argument("nonsensical vpub_old value");
        }

        if (vpub_new > MAX_MONEY) {
            throw std::invalid_argument("nonsensical vpub_new value");
        }

        uint64_t lhs_value = vpub_old;
        uint64_t rhs_value = vpub_new;

        for (size_t i = 0; i < NumInputs; i++) {
            // Sanity checks of input
            {
                // If note has nonzero value
                if (inputs[i].note.value() != 0) {
                    // The witness root must equal the input root.
                    if (inputs[i].witness.root() != rt) {
                        throw std::invalid_argument("joinsplit not anchored to the correct root");
                    }

                    // The tree must witness the correct element
                    if (inputs[i].note.cm() != inputs[i].witness.element()) {
                        throw std::invalid_argument("witness of wrong element for joinsplit input");
                    }
                }

                // Ensure we have the key to this note.
                if (inputs[i].note.a_pk != inputs[i].key.address().a_pk) {
                    throw std::invalid_argument("input note not authorized to spend with given key");
                }

                // Balance must be sensical
                if (inputs[i].note.value() > MAX_MONEY) {
                    throw std::invalid_argument("nonsensical input note value");
                }

                lhs_value += inputs[i].note.value();

                if (lhs_value > MAX_MONEY) {
                    throw std::invalid_argument("nonsensical left hand size of joinsplit balance");
                }
            }

            // Compute nullifier of input
            out_nullifiers[i] = inputs[i].nullifier();
        }

        // Sample randomSeed
        out_randomSeed = random_uint256();

        // Compute h_sig
        uint256 h_sig = this->h_sig(out_randomSeed, out_nullifiers, pubKeyHash);

        // Sample phi
        uint252 phi = random_uint252();

        // Compute notes for outputs
        for (size_t i = 0; i < NumOutputs; i++) {
            // Sanity checks of output
            {
                if (outputs[i].value > MAX_MONEY) {
                    throw std::invalid_argument("nonsensical output value");
                }

                rhs_value += outputs[i].value;

                if (rhs_value > MAX_MONEY) {
                    throw std::invalid_argument("nonsensical right hand side of joinsplit balance");
                }
            }

            // Sample r
            uint256 r = random_uint256();

            out_notes[i] = outputs[i].note(phi, r, i, h_sig);
        }

        if (lhs_value != rhs_value) {
            throw std::invalid_argument("invalid joinsplit balance");
        }

        // Compute the output commitments
        for (size_t i = 0; i < NumOutputs; i++) {
            out_commitments[i] = out_notes[i].cm();
        }

        // Encrypt the ciphertexts containing the note
        // plaintexts to the recipients of the value.
        {
            ZCNoteEncryption encryptor(h_sig);

            for (size_t i = 0; i < NumOutputs; i++) {
                SproutNotePlaintext pt(out_notes[i], outputs[i].memo);

                out_ciphertexts[i] = pt.encrypt(encryptor, outputs[i].addr.pk_enc);
            }

            out_ephemeralKey = encryptor.get_epk();

            // !!! Payment disclosure START
            if (out_esk != nullptr) {
                \*out_esk = encryptor.get_esk();
            }
            // !!! Payment disclosure END
        }

        // Authenticate h_sig with each of the input
        // spending keys, producing macs which protect
        // against malleability.
        for (size_t i = 0; i < NumInputs; i++) {
            out_macs[i] = PRF_pk(inputs[i].key, i, h_sig);
        }

        if (makeGrothProof) {
            if (!computeProof) {
                return GrothProof();
            }

            GrothProof proof;

            CDataStream ss1(SER_NETWORK, PROTOCOL_VERSION);
            ss1 << inputs[0].witness.path();
            std::vector<unsigned char> auth1(ss1.begin(), ss1.end());

            CDataStream ss2(SER_NETWORK, PROTOCOL_VERSION);
            ss2 << inputs[1].witness.path();
            std::vector<unsigned char> auth2(ss2.begin(), ss2.end());

            librustzcash_sprout_prove(
                proof.begin(),

                phi.begin(),
                rt.begin(),
                h_sig.begin(),

                inputs[0].key.begin(),
                inputs[0].note.value(),
                inputs[0].note.rho.begin(),
                inputs[0].note.r.begin(),
                auth1.data(),

                inputs[1].key.begin(),
                inputs[1].note.value(),
                inputs[1].note.rho.begin(),
                inputs[1].note.r.begin(),
                auth2.data(),

                out_notes[0].a_pk.begin(),
                out_notes[0].value(),
                out_notes[0].r.begin(),

                out_notes[1].a_pk.begin(),
                out_notes[1].value(),
                out_notes[1].r.begin(),

                vpub_old,
                vpub_new
            );

            return proof;
        }

        if (!computeProof) {
            return ZCProof();
        }

        protoboard<FieldT> pb;
        {
            joinsplit_gadget<FieldT, NumInputs, NumOutputs> g(pb);
            g.generate_r1cs_constraints();
            g.generate_r1cs_witness(
                phi,
                rt,
                h_sig,
                inputs,
                out_notes,
                vpub_old,
                vpub_new
            );
        }

        // The constraint system must be satisfied or there is an unimplemented
        // or incorrect sanity check above. Or the constraint system is broken!
        assert(pb.is_satisfied());

        // TODO: These are copies, which is not strictly necessary.
        std::vector<FieldT> primary_input = pb.primary_input();
        std::vector<FieldT> aux_input = pb.auxiliary_input();

        // Swap A and B if it's beneficial (less arithmetic in G2)
        // In our circuit, we already know that it's beneficial
        // to swap, but it takes so little time to perform this
        // estimate that it doesn't matter if we check every time.
        pb.constraint_system.swap_AB_if_beneficial();

        std::ifstream fh(pkPath, std::ios::binary);

        if(!fh.is_open()) {
            throw std::runtime_error(strprintf("could not load param file at %s", pkPath));
        }

        return ZCProof(r1cs_ppzksnark_prover_streaming<ppzksnark_ppT>(
            fh,
            primary_input,
            aux_input,
            pb.constraint_system
        ));
    }
};
```
</br>
这上面的代码是源码中调用验证的代码，其它的相关代码，都可以依此来查看。相关的代码都在zcash目录中。其实应该详细的把这个目录下的代码分析一下，就会把整个流程弄得更清楚。


## 五、总结
通过三个链的匿名方式的比较，可以发现，其实区块链在匿名方向上从传统走向新技术的过程。其它的区块链的匿名的方式，或多或少也是如此，在新技术没有得到完全验证的前提下，适当的组合和局部创新便成了主流。
