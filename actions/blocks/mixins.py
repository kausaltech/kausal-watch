class ActionListPageBlockPresenceMixin:
    def contains_model_instance(self, instance, blocks):
        container_block_name = self.model_instance_container_blocks[instance._meta.model]
        container_blocks = (child for child in blocks if child.block_type == container_block_name)
        child_block_class = self.child_blocks[container_block_name]
        subblock_name = child_block_class.model_instance_container_blocks[instance._meta.model]
        for child in container_blocks:
            if child.value.get(subblock_name) == instance:
                return True
        return False

    def insert_model_instance(self, instance, blocks):
        block_name = self.model_instance_container_blocks[instance._meta.model]
        child_block = self.child_blocks[block_name]
        subblock_name = child_block.model_instance_container_blocks[instance._meta.model]
        blocks.append((block_name, {subblock_name: instance}))

    def remove_model_instance(self, instance, blocks):
        block_name = self.model_instance_container_blocks[instance._meta.model]
        child_block = self.child_blocks[block_name]
        subblock_name = child_block.model_instance_container_blocks[instance._meta.model]
        for i, block in enumerate(blocks):
            if (block.block_type == block_name and block.value[subblock_name] == instance):
                break
        else:
            raise ValueError(f"Model instance {instance} is not referenced in blocks")
        blocks.pop(i)
