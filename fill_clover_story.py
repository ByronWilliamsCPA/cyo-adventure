#!/usr/bin/env python3
"""Fill the Clover and Butterfly skeleton with prose."""

import json
import sys

# Prose content for each node (replacing <<FILL>> directives)
# Writing for grade 1.0: very short sentences, simple words, 1-2 syllables
PROSE = {
    "n_start": "Clover is a little kitten. She sat in a sunny garden. A blue butterfly flew past! It went by some flowers. It went by a pond. It went to tall grass. Clover saw it. She wanted to go after it! Which way should she go?",

    "n_daisies": "The butterfly danced over white flowers. It went to more white flowers. A bee was there! The bee went buzz, buzz. It went from flower to flower. Then the butterfly went away. It went to a bird bath. What did Clover do?",

    "n_bee_end": "Clover stayed. She watched the bee. Buzz, buzz, buzz! The bee went on each flower. It was fun to watch. Then Clover looked up. The blue butterfly was gone. But Clover was happy. She went back home.",

    "n_birdbath": "A little bird was at the bird bath. The bird was wet. It made splashes. The blue butterfly sat on the edge. Then it flew away. It went to red strawberries. Clover went after it.",

    "n_strawberries": "Red berries sat under green leaves. They were sweet. The butterfly went over them. Then it went to a new spot. It went to a patch of soft green leaves. Clover came near.",

    "n_meadow": "The butterfly went very slow. It went right to Clover's nose! It stopped there. Clover could see it! A small ring of flowers was close by. Clover sat still. She did not move.",

    "n_nose_end": "The butterfly sat on Clover's nose! Its wings went up and down. Up and down. Clover giggled! Haha! She stayed still. She was so happy. The best day ever!",

    "n_crown_end": "Clover found a small ring of flowers. It was like a crown! It fit her head. The butterfly went around it once, so gentle. Clover put on the crown. She was so proud!",

    "n_pond": "There was a pond. A green frog was on a lily pad. It had big eyes. The butterfly went over the water. It went to some reeds. What did Clover do?",

    "n_frog_end": "Clover and the frog played. They played peek-a-boo! Splash! Hop! The frog went this way. Clover went that way. They had fun. But the butterfly flew away. Clover went home. She was tired. She was happy too.",

    "n_reeds": "The butterfly went through green reeds. The reeds went swish, swish. A dragonfly went by! Zoom! It was like a helicopter! The butterfly went on. There was a log with moss.",

    "n_hedgehog": "Under the log was a little ball. It was a hedgehog! It was asleep. Clover went very quiet. She did not wake it up. She went on after the butterfly. The shade was cool there.",

    "n_friend": "A little bunny was in the shade. Its name was Pip. Pip was nibbling sweet green leaves. Nom, nom, nom! The butterfly sat on a leaf up high. Pip saw Clover. Pip said hello.",

    "n_share_end": "Clover and Pip found red berries. They ate them together. Munch, munch, munch! The butterfly sat and watched. Two new friends. Sticky paws. A nice day outside. The best time ever!",

    "n_grass": "Tall grass was all around. The butterfly went up and down. Like a kite! The grass was soft. Clover could run fast. Or she could go slow and quiet. What did she do?",

    "n_lost_end": "Clover ran very fast! Her paws went tap, tap, tap. The butterfly went up high. Up over a fence! Clover could not go there. So she went back home. She was happy and tired.",

    "n_sunflower": "Tall yellow sunflowers were all around. They moved in the wind. The butterfly went through them. It went to a gate. The gate was made of wood. Clover went after it.",

    "n_gate": "The butterfly went through the gate. Clover went through too! Flowers were there. Pink ones. Purple ones. So many! So pretty!",

    "n_arch": "A green arch was over them. It had sweet flowers. The butterfly went under it. Around and around. Then it sat still. It waited for Clover!",

    "n_perch_end": "Clover sat under the arch. The butterfly sat on her ear! Like a bow! They sat there. It was cool. It was nice. They were so glad. The best day of all!",
}

def fill_skeleton(skeleton_path: str, output_path: str) -> None:
    """Load skeleton and fill with prose."""
    with open(skeleton_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Fill each node
    for node in data['nodes']:
        node_id = node['id']
        if node_id in PROSE:
            node['body'] = PROSE[node_id]

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Filled skeleton written to {output_path}")

if __name__ == '__main__':
    skeleton = "/home/user/cyo-adventure/skeletons/3-5/the-clover-and-the-butterfly.json"
    output = "/home/user/cyo-adventure/out/the-clover-and-the-butterfly.filled.json"
    fill_skeleton(skeleton, output)
