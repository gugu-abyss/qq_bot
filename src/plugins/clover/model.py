import torch
from transformers.models.gpt2.modeling_gpt2 import GPT2LMHeadModel
from transformers import BertTokenizer
import torch.nn.functional as F

tokenizer = BertTokenizer(vocab_file="./GPT2-chitchat/vocabulary/vocab_small.txt")
model = GPT2LMHeadModel.from_pretrained("./GPT2-chitchat/dialogue_model_path")
model.to('cpu')
model.eval()


def top_k_top_p_filtering(logits, top_k: int = 0, top_p: float = 0.0, filter_value=-float('Inf')):
    """ Filter a distribution of logits using top-k and/or nucleus (top-p) filtering
        Args:
            logits: logits distribution shape (vocabulary size)
            top_k > 0: keep only top k tokens with highest probability (top-k filtering).
            top_p > 0.0: keep the top tokens with cumulative probability >= top_p (nucleus filtering).
                Nucleus filtering is described in Holtzman et al. (http://arxiv.org/abs/1904.09751)
        From: https://gist.github.com/thomwolf/1a5a29f6962089e871b94cbd09daf317
        :param logits:
        :param filter_value:
        :param top_p:
        :param top_k:
    """
    assert logits.dim() == 1  # batch size 1 for now - could be updated for more but the code would be less clear
    top_k = min(top_k, logits.size(-1))  # Safety check
    if top_k > 0:
        # Remove all tokens with a probability less than the last token of the top-k
        # torch.topk()返回最后一维最大的top_k个元素，返回值为二维(values,indices)
        # ...表示其他维度由计算机自行推断
        indices_to_remove = logits < torch.topk(logits, top_k)[0][..., -1, None]
        logits[indices_to_remove] = filter_value  # 对于topk之外的其他元素的logits值设为负无穷

    if top_p > 0.0:
        sorted_logits, sorted_indices = torch.sort(logits, descending=True)  # 对logits进行递减排序
        cumulative_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)

        # Remove tokens with cumulative probability above the threshold
        sorted_indices_to_remove = cumulative_probs > top_p
        # Shift the indices to the right to keep also the first token above the threshold
        sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
        sorted_indices_to_remove[..., 0] = 0

        indices_to_remove = sorted_indices[sorted_indices_to_remove]
        logits[indices_to_remove] = filter_value
    return logits


def predict(text: str) -> str:
    history = [tokenizer.encode(text)]

    input_ids = [tokenizer.cls_token_id]  # 每个input以[CLS]为开头

    for history_id, history_utr in enumerate(history[-5:]):
        input_ids.extend(history_utr)
        input_ids.append(tokenizer.sep_token_id)
    curr_input_tensor = torch.tensor(input_ids).long().to('cpu')
    generated = []
    # 最多生成max_len个token
    for _ in range(25):
        outputs = model(input_ids=curr_input_tensor)
        next_token_logits = outputs[0][-1, :]
        # 对于已生成的结果generated中的每个token添加一个重复惩罚项，降低其生成概率
        for id in set(generated):
            next_token_logits[id] /= 1.0
        next_token_logits = next_token_logits / 1
        # 对于[UNK]的概率设为无穷小，也就是说模型的预测结果不可能是[UNK]这个token
        next_token_logits[tokenizer.convert_tokens_to_ids('[UNK]')] = -float('Inf')
        filtered_logits = top_k_top_p_filtering(next_token_logits, top_k=8, top_p=0)
        # torch.multinomial表示从候选集合中无放回地进行抽取num_samples个元素，权重越高，抽到的几率越高，返回元素的下标
        next_token = torch.multinomial(F.softmax(filtered_logits, dim=-1), num_samples=1)
        if next_token == tokenizer.sep_token_id:  # 遇到[SEP]则表明response生成结束
            break
        generated.append(next_token.item())
        curr_input_tensor = torch.cat((curr_input_tensor, next_token), dim=0)
        # his_text = tokenizer.convert_ids_to_tokens(curr_input_tensor.tolist())
        # print("his_text:{}".format(his_text))
    history.append(generated)
    text = tokenizer.convert_ids_to_tokens(generated)
    return "".join(text)


if __name__ == "__main__":
    print(predict("好了, 我把图片识别的关掉了, 2g的内存一下子用掉了1.9"))
